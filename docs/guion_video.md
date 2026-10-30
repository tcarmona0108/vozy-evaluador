# Guion del video (≈4:45 min)

> Antes de grabar: abrir https://vozy-evaluador-lina.onrender.com/health para despertar el servicio (plan gratuito)
> y pulsar una vez "¡Evaluar!" en la UI para que el lote quede en caché y la demo sea instantánea (la caché se pierde si el servicio se suspende tras 15 min sin uso).
> Pestañas listas: UI, Swagger, README en GitHub, `results.json`, `HALLAZGOS.md`.

## 0:00 – 0:40 · Problema y enfoque
- "Vozy necesita saber cuándo un agente de voz incumple las reglas del cliente. El caso es Lina, que cobra para Banco
  Andino con 10 reglas, y 20 llamadas simuladas."
- "Construí un servicio que evalúa cada llamada contra 13 criterios, con una cita literal como evidencia de cada
  falla, un puntaje, una severidad y un reporte agregado."
- "La idea central es que lo objetivo lo decide el código y lo semántico el LLM. Nunca publico una cita que no esté
  textual en la transcripción."

## 0:40 – 1:40 · Demo en la URL pública
- **UI** (`/ui`): mostrar el encabezado con la identidad de Vozy y los 3 pasos del enfoque; sin subir archivo, pulsar **¡Evaluar!** (evalúa las 20 de la prueba). Mencionar que se puede subir otro `.json` con la misma estructura.
  - Tarjetas de indicadores: puntaje promedio, cumplimiento de criterios, llamadas con falla crítica y distribución de severidad.
  - Tabla por conversación: puntaje, severidad y ✅/❌ por criterio.
  - Pestaña *Fallas con evidencia*: mostrar C20 R2b ("el cliente dice 6295, el registro es 6259") y C14 R10
    ("centrales de riesgo… embargo").
  - Pestaña *Reporte agregado*: tasa por criterio y ranking por impacto. Descargar `results.json`.
- **Swagger** (`/docs`): `POST /evaluate` con una conversación; mostrar el JSON con `criterios`, `evidencia` (turno +
  texto), `severidad_global` y `metadatos` (modelo, tokens, latencia, discrepancias). Enviar un JSON mal formado y
  mostrar el **422** con el campo que falta.

## 1:40 – 2:40 · Arquitectura híbrida y por qué
- Mostrar el diagrama del README.
- "Una sola llamada a Gemini por conversación. Antes, el código calcula hechos: si se presentó, si pidió los dígitos
  y si coinciden (también dichos en palabras), el monto con un parser de números en español, las fechas y los
  términos prohibidos."
- "El LLM recibe esos hechos y juzga lo semántico: si quien atiende es el titular, si hubo presión, si escaló bien,
  si el cierre resume. Responde JSON con esquema y lo valido con Pydantic."
- "Si ambos opinan sobre algo objetivo, gana el código y queda registrada la discrepancia. Ejemplo: la fecha del
  compromiso la saca el código de la confirmación del agente."
- "Si el LLM falla (cuota, 5xx, JSON inválido): reintentos, una cadena de modelos de respaldo y, en último caso,
  modo degradado. Los criterios de código se evalúan igual y el servicio nunca se cae."

## 2:40 – 3:40 · Rúbrica y precisión medida
- "Separé R1, R2 y R4 porque mezclan obligaciones que fallan por separado. Por ejemplo, verificar los dígitos es un
  riesgo de privacidad, mientras que confirmar el nombre es de forma."
- "Cada criterio tiene una condición de aplicabilidad, y una falla se penaliza solo en su regla de origen."
- "Severidad en tres niveles y un puntaje ponderado; la severidad es la señal principal porque el puntaje diluye una
  falla crítica."
- Mostrar la tabla de precisión: **259/260 etiquetas, 22/22 fallas, 0 falsos positivos, severidad 20/20**.
- "Iteré con reglas generales, nunca por id: por ejemplo, definí qué es insistir para R10. Además validé con 5
  conversaciones sintéticas (dígitos en pares, monto en cifras, un agente que menciona un abogado): 64 de 64."
- "El único desacuerdo, C06 R7, es un caso de frontera que dejé documentado en vez de sobreajustar."

## 3:40 – 4:20 · Hallazgos para el cliente
- Abrir `HALLAZGOS.md`:
  1. "Revela la deuda sin verificar identidad (15 %, crítica): una herramienta que bloquee los datos de la deuda
     hasta verificar."
  2. "Amenazas y presión (15 %, crítica): filtro de frases prohibidas y disparador de escalamiento."
  3. "Compromisos inválidos (15 %, grave): una función que valide la fecha y leer monto y fecha desde variables."
- "Cada ajuste trae su métrica. Este mismo evaluador sirve para medir si mejoró."

## 4:20 – 4:45 · Limitaciones y costo
- "Despliegue en Render gratis: Hugging Face ahora exige plan PRO para Docker. Hay un arranque en frío de un minuto."
- "El tier gratuito de Gemini da 20 solicitudes diarias por modelo; por eso la cadena de respaldo. El LLM no es
  determinista, por eso lo objetivo lo decide el código."
- "Costo: entre 3 y 10 dólares por cada 1.000 llamadas en el tier pago. Con datos reales de un banco usaría el tier
  pago o Vertex AI, porque en el gratuito Google puede usar los datos."
- Cierre: "El repo, el README y `results.json` están en el enlace. Gracias."
