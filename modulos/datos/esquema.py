"""
Las tres tablas de un semestre y qué guarda cada una.

    alumnos.csv      quiénes son          (casi no cambia)
    notas.csv        en qué van           (estado; se lee y se escribe todo el tiempo)
    log_envios.csv   qué pasó y cuándo    (append-only; solo se escribe)

Viven en la raíz del semestre, no dentro de tests_semanales/ o tareas/, porque
ahora son compartidas: la columna Flujo distingue de cuál viene cada fila.
"""

ALUMNOS = "alumnos.csv"
NOTAS = "notas.csv"
LOG = "log_envios.csv"

# Quiénes son. Refleja el archivo que sube el profesor; el sistema solo le
# agrega el grupo cuando lo asigna.
COLUMNAS_ALUMNOS = ["Nombre", "Correo", "Grupo"]

# En qué van. Formato largo: una fila por alumno-ítem, en vez de una columna
# por semana como antes (que llegaba a 55 columnas al cerrar el semestre).
# "Item" es la semana en tests ("3") o la tarea en tareas ("T1").
COLUMNAS_NOTAS = [
    "Correo", "Flujo", "Item",
    "Enviado",        # ISO 8601, vacío si todavía no se le envió
    "Respondio",      # ISO 8601, vacío si no ha respondido
    "Nota", "Originalidad",
    # Para la revisión docente y la escala de notas. Las filas viejas los tienen
    # vacíos y se leen igual que antes.
    "Corregido",      # ISO 8601: cuándo quedó la corrección (del modelo o del docente).
                      # Con Nota vacía significa "corregida, sin enviar".
    "Logro",          # de 0 a 1, con cuatro decimales (tests); vacío en tareas y en
                      # ajustes fuera de escala
    "Descartada",     # ISO 8601: el docente decidió no mandar feedback
]

# Qué pasó. Una fila por EVENTO, nunca se edita ni se reescribe: solo se agrega
# al final. Eso lo hace seguro cuando dos personas trabajan en paralelo (basta
# concatenar los archivos y deduplicar) y permite reconstruir la historia
# completa, incluidos los reintentos y los errores.
EVENTOS = (
    "envio",        # se le mandó la pregunta de la semana
    "respuesta",    # el alumno contestó
    "evaluacion",   # el agente la corrigió y le mandó el feedback
    "repregunta",   # el alumno preguntó algo sobre ese feedback
    "tutoria",      # el agente le respondió la duda, sin tocar la nota
    "ajuste",       # alguien del equipo docente cambió la nota a mano (motivo en Detalle)
    "feedback",     # salió el correo de una corrección que se guardó para revisarla antes
                    # (tareas, 2026-2). Ya no se escribe: ahora es una 'evaluacion' con MessageId.
    "error",
    "correccion",   # la corrección propuesta (del modelo o del docente), antes de mandarla
    "descarte",     # el docente decidió no mandar feedback (motivo y quién en Detalle)
    "recalculo",    # la nota cambió porque cambió la escala del semestre
)

COLUMNAS_LOG = [
    "Timestamp",      # cuándo se registró el evento
    "Semestre", "Flujo", "Item", "Correo",
    "Evento",         # uno de EVENTOS
    "MessageId",      # id del mensaje que produjo este evento, para reconocer
                      # después lo que responda el alumno
    "RespondeA",      # id del mensaje al que este contesta; encadena la conversación
    "Ronda",          # 0 el ciclo normal, 1..N cada vuelta de tutoría
    "Modelo",         # qué modelo lo produjo
    "Versiones",      # con qué se produjo: prompt, pauta, plantilla del correo y
                      # parámetros, cada uno nombre@huella (modulos/ia/versiones.py)
    "TokensEntrada",  # lo que costó la llamada, para poder medirlo después
    "TokensSalida",
    "Nota", "Originalidad",
    "Respuesta",      # lo que escribió el alumno ('respuesta' y 'repregunta')
    "EvaluacionIA",   # lo que devolvió el modelo ('evaluacion' y 'tutoria')
    "Detalle",        # en 'error': el mensaje
    "Puntajes",       # puntaje de cada pregunta, separados por ";" (p. ej. "3;2;0.5")
    "Logro",          # de 0 a 1: puntaje obtenido / puntaje máximo
]

# Eventos que son un mensaje del alumno, y su contraparte del agente.
DEL_ALUMNO = ("respuesta", "repregunta")
# Un 'ajuste' solo calza con un correo del alumno cuando se le avisó (trae MessageId).
DEL_AGENTE = ("evaluacion", "tutoria", "ajuste")

# Los dos flujos del curso
TESTS = "test"
TAREAS = "tarea"
