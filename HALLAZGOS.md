# Hallazgos: agente de cobranza "Lina" — Banco Andino

**Para:** equipo de Cobranzas y Cumplimiento, Banco Andino · **Base:** 20 llamadas del 22-sep-2026, evaluadas
automáticamente contra 13 criterios derivados de las 10 reglas del agente (detalle y evidencia en `results.json`).

**Resumen.** 7 de 20 llamadas (35 %) tienen al menos una falla crítica y solo 7 (35 %) cumplen todo. El agente
maneja bien los casos difíciles cuando los reconoce (terceros, sospecha de fraude, "ya pagué", pedidos de
refinanciación), pero falla en tres controles que hoy dependen de que el modelo "se acuerde": verificar la
identidad, no presionar y validar la fecha del compromiso. Las priorizo por **impacto** (severidad × frecuencia).

## 1. Revela la deuda sin verificar la identidad — crítica, 15 % de las llamadas

**Qué pasa.** En C02 y C19 el agente informa saldo, producto y fecha sin pedir los últimos 4 dígitos ("Marcela, su
préstamo de libre inversión tiene un saldo vencido de ochocientos treinta mil pesos…"). En C20 el cliente dice
**6295**, el registro termina en **6259**, y el agente continúa como si coincidieran.
**Riesgo.** Divulgar información financiera a quien no está verificado expone al banco a reclamos por protección de
datos personales y a fraude por suplantación.
**Ajuste recomendado.**
- *Configuración:* una herramienta determinista `verificar_identidad(digitos)` que compara contra el registro, y la
  plataforma **no entrega al modelo monto, producto ni fechas** hasta que la herramienta responda `verificado=true`.
  Si no coincide, se permite un reintento y luego se ofrece otro canal.
- *Prompt:* "No menciones saldo, producto ni fechas antes de que `verificar_identidad` confirme. Nunca supongas que
  los dígitos coinciden."

**Cómo medirlo.** Cumplimiento de R2b del 82 % al 100 % en la siguiente muestra, más un set de prueba con dígitos
transpuestos y dichos en palabras.

## 2. Amenazas y presión indebida — crítica, 15 % de las llamadas

**Qué pasa.** En C14 el agente dice: "si no paga pronto será reportada a centrales de riesgo y el banco puede iniciar
un proceso de embargo". En C09 menciona el "cobro jurídico" a un cliente que asegura haber pagado y tener el recibo.
En C07 el cliente pide dos veces hablar con una persona y el agente insiste dos veces en la fecha de pago, hasta que
el cliente cuelga.
**Riesgo.** Prácticas de cobro abusivas: quejas ante el supervisor financiero y daño reputacional. Además, la presión
no produjo pagos (C07 y C09 terminan sin compromiso).
**Ajuste recomendado.**
- *Configuración:* un filtro de salida con una **lista de frases prohibidas** (cobro jurídico, embargo, centrales de
  riesgo, abogado, demanda, reporte) que bloquea la respuesta y la regenera. Además, un **disparador de
  escalamiento**: ante un pedido de asesor, una disputa o "ya pagué", transferir o registrar el caso de inmediato.
- *Prompt:* "Ante una negativa, un pedido de asesor o un 'ya pagué', haz como máximo una pregunta sobre el pago y
  luego escala. Nunca menciones consecuencias legales ni reportes."

**Cómo medirlo.** Cero menciones prohibidas y cumplimiento de R10 del 85 % al 100 %. R7 (escalamiento) pasa del
60 % al 100 % en las llamadas donde aplica.

## 3. Compromisos de pago inválidos — grave, 15 % de las llamadas

**Qué pasa.** El agente registra lo que diga el cliente: una fecha 12 días después de la llamada (C10, 4 de octubre,
cuando el máximo es 5), una fecha **anterior** a la llamada (C17, "lunes 21", a pedido del cliente) y un compromiso
sin fecha concreta (C19, "El sábado").
**Riesgo.** Promesas que no se pueden gestionar: seguimientos que vencen mal, indicadores de recuperación inflados y
registros que no sirven como soporte ante el cliente.
**Ajuste recomendado.**
- *Configuración:* una función `registrar_compromiso(fecha)` que **rechaza** fechas pasadas, posteriores a 5 días o
  sin día y mes. El agente solo puede registrar a través de ella.
- *Prompt:* "Si la fecha no es válida, propone dos fechas concretas dentro de la ventana."
- *Datos:* que el agente **lea monto y fecha de vencimiento desde variables** en lugar de generarlos. En C11 dijo
  2.620.000 en vez de 2.260.000 y en C19 informó el 21 de septiembre en vez del 12.

**Cómo medirlo.** Cumplimiento de R5 del 75 % al 100 % y 0 compromisos fuera de la ventana en el registro. R4a y R4b
al 100 %.

**También:** 4 de 19 llamadas (21 %) cierran sin resumen ("Listo.", "Gracias, hasta luego."). Una plantilla de
cierre con monto, fecha y gestión registrada lo resuelve con bajo esfuerzo.

**Siguiente paso.** Aplicar los tres ajustes, volver a correr este evaluador sobre una muestra semanal de llamadas y
revisar juntos la tendencia por criterio.
