# Hallazgos: agente de cobranza "Lina" — Banco Andino

**Para:** Cobranzas y Cumplimiento, Banco Andino · **Base:** 20 llamadas del 22-sep-2026, evaluadas contra 13
criterios derivados de las 10 reglas del agente (evidencia completa en `results.json`).

**Resumen.** 7 de 20 llamadas (35 %) tienen al menos una falla crítica y solo 7 cumplen todo. Lina maneja bien
terceros, sospechas de fraude y pedidos de refinanciación, pero falla en tres controles que hoy dependen de que el
modelo "se acuerde". Los priorizo por **impacto** (severidad × frecuencia).

## 1. Revela la deuda sin verificar la identidad — crítica, 15 % de las llamadas

**Qué pasa.** En C02 y C19 informa saldo y producto sin pedir los últimos 4 dígitos. En C20 la clienta dice
**6295**, el registro termina en **6259**, y Lina continúa como si coincidieran.
**Riesgo.** Divulgar datos financieros a alguien no verificado: reclamos por protección de datos y fraude por
suplantación.
**Ajuste.** *Configuración:* una herramienta `verificar_identidad(digitos)` que compara contra el registro; el modelo
**no recibe monto, producto ni fechas** hasta que responda `verificado=true` (un reintento y luego otro canal).
*Prompt:* "No menciones saldo, producto ni fechas antes de que `verificar_identidad` confirme."
**Meta.** R2b del 82 % al 100 %, probado también con dígitos transpuestos y dichos en palabras.

## 2. Amenazas y presión indebida — crítica, 15 % de las llamadas

**Qué pasa.** En C14: "si no paga pronto será reportada a centrales de riesgo y el banco puede iniciar un proceso de
embargo". En C09 menciona el "cobro jurídico" a un cliente que dice tener el recibo. En C07 el cliente pide dos
veces un asesor y Lina insiste dos veces en la fecha, hasta que cuelga.
**Riesgo.** Prácticas de cobro abusivas: quejas ante el supervisor y daño reputacional. Además, la presión no
produjo pagos: C07 y C09 terminan sin compromiso.
**Ajuste.** *Configuración:* un filtro de salida con **frases prohibidas** (cobro jurídico, embargo, centrales de
riesgo, demanda) que regenera la respuesta, y un **disparador de escalamiento** ante pedido de asesor, disputa o
"ya pagué". *Prompt:* "Ante una negativa, un pedido de asesor o un 'ya pagué', pregunta como máximo una vez por el
pago y luego escala. Nunca menciones consecuencias legales ni reportes."
**Meta.** Cero menciones prohibidas; R10 del 85 % al 100 % y R7 (escalamiento) del 60 % al 100 %.

## 3. Compromisos de pago inválidos — grave, 15 % de las llamadas

**Qué pasa.** Lina registra lo que diga el cliente: 12 días después de la llamada (C10, cuando el máximo es 5), una
fecha **anterior** a la llamada (C17, "lunes 21") y "El sábado", sin fecha concreta (C19).
**Riesgo.** Seguimientos que vencen mal, indicadores de recuperación inflados y registros sin valor como soporte.
**Ajuste.** *Configuración:* `registrar_compromiso(fecha)` **rechaza** fechas pasadas, a más de 5 días o sin día y
mes; Lina solo registra a través de ella. *Prompt:* "Si la fecha no es válida, propone dos fechas dentro de la
ventana." *Datos:* leer monto y vencimiento desde variables, no generarlos (C11 dijo 2.620.000 en vez de 2.260.000;
C19, el 21 de septiembre en vez del 12).
**Meta.** R5 del 75 % al 100 % y 0 compromisos fuera de la ventana; R4a y R4b al 100 %.

**También:** 4 de 19 llamadas cierran sin resumen ("Listo.", "Gracias, hasta luego."); una plantilla de cierre con
monto, fecha y gestión registrada lo resuelve con poco esfuerzo.

**Siguiente paso.** Aplicar los tres ajustes, correr este evaluador sobre una muestra semanal y revisar juntos la
tendencia por criterio.
