Hola, Tomás. Espero que estés muy bien.

Gracias por tu tiempo en la primera entrevista. Como siguiente paso del proceso, te comparto la prueba técnica. Adjunto encontrarás el archivo conversaciones_prueba_fde.json con todo lo necesario.

CONTEXTO
En Vozy desplegamos agentes de IA de voz y WhatsApp para empresas de Latinoamérica. Una parte clave del trabajo de un FDE es asegurar la calidad de esos agentes en producción: detectar cuándo un agente incumple las reglas del cliente y proponer cómo corregirlo.

El archivo adjunto contiene:

La especificación de “Lina”, un agente de cobranza por voz de un banco ficticio (Banco Andino), con 10 reglas de negocio (R1 a R10).
20 transcripciones de llamadas simuladas, cada una con los datos del cliente que el agente tenía disponibles.
EL RETO
Construye y publica un servicio que evalúe automáticamente cada conversación contra una rúbrica diseñada por ti, basada en las reglas del agente.

Para cada conversación, el servicio debe devolver:

Por cada criterio de tu rúbrica: resultado (cumple / no cumple / no aplica), la cita textual de la transcripción que lo justifica y una explicación breve.
Un puntaje global de la conversación y una severidad de las fallas encontradas (por ejemplo: leve / grave).
Además, el servicio debe generar un reporte agregado de las 20 conversaciones: tasa de cumplimiento por criterio y las fallas más frecuentes.

REQUISITOS FUNCIONALES
Una forma de evaluar una conversación individual y una forma de evaluar el archivo completo. Puede ser una API (por ejemplo, POST /evaluate y POST /evaluate/batch con documentación Swagger) o una interfaz simple (Streamlit o Gradio) donde se pueda subir el JSON.
La salida debe ser JSON estructurado y validado (por ejemplo, con Pydantic o JSON Schema), con un formato consistente en todas las conversaciones.
La evaluación debe considerar tanto la transcripción como los datos del cliente y la especificación del agente.
REQUISITOS TÉCNICOS
Lenguaje libre.
Puedes usar cualquier LLM. Para no incurrir en costos, te recomendamos el tier gratuito de Google Gemini.
Publícalo en una plataforma gratuita (Hugging Face Spaces, Render, Railway, Vercel o similar). No debe requerir ninguna inversión.
Las credenciales deben estar en variables de entorno. Ninguna API key en el repositorio.
Manejo de errores: si el LLM falla o devuelve una respuesta inválida, el servicio no debe caerse.
Puedes combinar validaciones con código y evaluación con LLM. Si lo haces, explica en el README qué resolviste de cada forma y por qué.
Puedes usar herramientas de IA para programar. Esperamos que entiendas y puedas defender cada decisión.
ENTREGABLES
a) URL pública del servicio funcionando.
b) Repositorio público en GitHub.
c) Archivo results.json con la evaluación de las 20 conversaciones, generado por tu servicio.
d) README que incluya:

Arquitectura y cómo correrlo localmente.
Tu rúbrica: qué criterios definiste y por qué.
Decisiones técnicas y limitaciones conocidas.
Costo estimado de evaluar 1.000 conversaciones con tu solución.
e) Una sección de hallazgos, escrita como si se la enviaras al cliente (máximo una página): las 3 fallas más importantes del agente y qué ajustes recomendarías en su prompt o configuración.
f) Video de 3 a 5 minutos (Loom o similar) mostrando el servicio y explicando tus decisiones principales.
CRITERIOS DE ENTREGA
La entrega se considera completa solo si cumple todo lo siguiente:

La URL pública responde y permite evaluar el archivo adjunto sin intervención manual.
Se evalúan las 20 conversaciones y results.json es un JSON válido con el mismo formato en todas.
Cada criterio marcado como “no cumple” incluye una cita textual de la transcripción como evidencia.
El repositorio no contiene API keys ni credenciales.
README, hallazgos y video están incluidos.
Se entrega antes del plazo indicado abajo.
CÓMO LO VAMOS A EVALUAR
Precisión de la evaluación (30%): qué tan bien detecta tu servicio las fallas reales y evita falsos positivos.
Diseño de la rúbrica (20%): cobertura de las reglas, criterios claros y manejo de casos que no aplican.
Calidad técnica (20%): código, estructura, validación de la salida y manejo de errores.
Hallazgos y comunicación (15%): claridad y utilidad de tus recomendaciones para el cliente.
Despliegue y documentación (15%): servicio funcionando, README y video.
PLAZO Y ENTREGA
Tiempo estimado de trabajo: entre 6 y 8 horas.
Fecha límite: 24 horas a partir del envío de este correo.
Envía los links (URL, repositorio y video) respondiendo a este correo.
Si tienes cualquier duda sobre el enunciado, escríbeme a este correo. Preguntar también es parte de la prueba.

¡Mucho éxito!