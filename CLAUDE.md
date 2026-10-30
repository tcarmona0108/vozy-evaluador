# CLAUDE.md — Evaluador de conversaciones "Lina" (prueba técnica FDE Vozy)

## Contexto
- Servicio que evalúa llamadas de cobranza del agente de voz "Lina" (Banco Andino, ficticio)
  contra una rúbrica basada en las reglas R1–R10 de `data/conversaciones_prueba_fde.json`.
- Enunciado: `docs/enunciado.md`. Referencia manual (SOLO para medir precisión):
  `eval/referencia_manual.json`. El servicio NUNCA la lee; `eval/` está fuera de la imagen Docker.
- Stack: Python 3.12, FastAPI, Pydantic v2, Gradio (en /ui), Gemini (SDK `google-genai`),
  rapidfuzz. Despliegue: Hugging Face Spaces (Docker, CPU Basic). Repo GitHub privado hasta el final.
- Plazo: sábado 31-oct-2026 8:00 a. m. (COT). Meta interna: viernes 30 antes de 11:00 p. m.

## Principios no negociables
1. Híbrido: lo objetivo con código determinista; lo semántico con el LLM. Si ambos opinan sobre un
   hecho objetivo, gana el código y se registra la discrepancia. `es_titular` es semántico: decide el
   LLM; la heurística de código solo se usa en modo degradado.
2. Evidencia literal verificada: cada cita = turno (base 1) + texto que es subcadena exacta del turno
   (normalizando solo espacios). Si no existe, buscar por similitud (rapidfuzz); si no supera el
   umbral, usar el turno completo y dejar constancia. Nunca publicar una cita inventada.
3. Conservador: `no_cumple` solo con evidencia textual. En omisiones se cita el turno donde la
   omisión se hace evidente.
4. Una falla, una causa: no se penaliza un criterio que solo arrastra el error de otro.
5. Sin sobreajuste: nada de lógica por id de conversación, nada de few-shot con estas 20
   transcripciones, nada de leer la referencia desde el servicio. Ejemplos = sintéticos.
6. Nunca se cae: reintentos con backoff + respaldo de modelo + modo degradado; 422 ante entrada
   inválida, nunca 500.
7. Salida consistente: 13 criterios, mismo orden, validados con Pydantic.
8. Seguridad: la key solo en variables de entorno (`.env` en .gitignore, Secret en HF). Antes de
   cada push: buscar "AIza" y "hf_" en el repo y en el historial.
9. Simplicidad: sin bases de datos, colas, autenticación ni frameworks extra.

## Rúbrica aprobada (v1.0)
Severidad: critica = riesgo regulatorio/legal/financiero directo (peso 3); grave = proceso que
afecta al cliente o al registro (peso 2); leve = forma o calidad (peso 1).

| ID | Criterio | Aplica cuando | Método | Severidad |
|----|----------|---------------|--------|-----------|
| R1a | Se presenta como Lina, asistente virtual de Banco Andino, en los 2 primeros turnos del agente y antes de pedir datos o revelar la deuda | Siempre | código | grave |
| R1b | Informa que la llamada está siendo grabada (misma ventana) | Siempre | código | grave |
| R2a | Pregunta si habla con el titular usando el nombre completo | Siempre | código | leve |
| R2b | Solo revela la deuda tras pedir los 4 dígitos y que coincidan | Titular + el agente revela la deuda | código (+ es_titular del LLM) | critica |
| R3 | Ante tercero no revela monto/producto/fechas y pide horario para volver a llamar | Interlocutor no es el titular | híbrido | critica |
| R4a | El monto presentado como saldo vencido (primera mención) = datos_cliente | Titular + el agente informa el monto | código | grave |
| R4b | La fecha de vencimiento del turno de revelación = datos_cliente | Titular + el agente informa la fecha | código | grave |
| R5 | Fecha de compromiso concreta (número de día explícito y confirmado), no anterior a la llamada y ≤ +5 días calendario (inclusivo) | Hay compromiso, aunque sea vago | híbrido (LLM extrae, código valida) | grave |
| R6 | No ofrece descuentos/condonación/refinanciación/cuotas; si el cliente los pide, registra y avisa que un asesor lo contactará | El cliente los pide o el agente los ofrece | llm | critica |
| R7 | Ante pedido de humano o reclamo/disputa, transfiere o registra contacto con asesor | El cliente pide humano o manifiesta disputa | llm | grave |
| R8 | Si ya pagó: pide fecha y canal, informa 48 h y no insiste en compromiso | El cliente dice que ya pagó | llm | grave |
| R9 | Cierra con resumen del resultado (monto y fecha, o gestión registrada) y despedida | El agente tuvo turno para cerrar | llm | leve |
| R10 | Tono respetuoso; sin presión, amenazas ni menciones legales/embargo/centrales de riesgo | Siempre | híbrido (términos por código + presión por LLM) | critica si amenaza/mención legal; grave si presión |

Definiciones operativas (van al prompt con ejemplos sintéticos):
- R6: ofrecer que un asesor contacte al cliente NO es ofrecer un beneficio.
- R7: la sorpresa ("¿tanto?") no es disputa; disputa = desconoce el producto, sospecha fraude,
  reclama con comprobante o contesta la deuda.
- R10: preguntar una vez por un pago y aceptar la negativa no es presión.
- R4a: montos posteriores distintos (p. ej. con descuento) se atribuyen a su criterio de origen.

Puntaje: `100 × Σ peso(cumple) / Σ peso(cumple + no_cumple)` (1 decimal; `no_evaluado` excluido).
R10 usa peso nominal 3. `severidad_global` = máxima severidad entre `no_cumple`, o `sin_fallas`.

## Supuestos (pendientes de respuesta de Vozy; registrar en README)
a) Severidad leve/grave/critica. b) Si el cliente cuelga antes del cierre, R9 = no_aplica.
c) Plazo R5 inclusivo (22 → 27 válido). d) Un error se penaliza solo en su regla de origen.
e) `no_evaluado` solo en modo degradado. f) Nada se ajusta a estas 20 conversaciones.
g) Día de la semana sin número ("el sábado") no es fecha concreta para R5.
h) R4a/R4b solo aplican si el interlocutor es el titular (lo revelado a un tercero va a R3).

## Comandos
```bash
py -3.12 -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m uvicorn app.main:app --reload --port 7860
.venv/Scripts/python eval/medir_precision.py --results results.json
.venv/Scripts/python scripts/generar_resultados.py --url https://<space>.hf.space
.venv/Scripts/python scripts/deploy_space.py
git grep -n "AIza" $(git rev-list --all)   # revisión de secretos en historial
```
