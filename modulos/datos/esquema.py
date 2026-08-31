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
]

# Qué pasó. Una fila por EVENTO, nunca se edita ni se reescribe: solo se agrega
# al final. Eso lo hace seguro cuando dos personas trabajan en paralelo (basta
# concatenar los archivos y deduplicar) y permite reconstruir la historia
# completa, incluidos los reintentos y los errores.
EVENTOS = ("envio", "respuesta", "evaluacion", "error")

COLUMNAS_LOG = [
    "Timestamp",      # cuándo se registró el evento
    "Semestre", "Flujo", "Item", "Correo",
    "Evento",         # uno de EVENTOS
    "MessageId",      # en 'envio': el id que permite reconocer la respuesta
    "Modelo",         # en 'evaluacion': qué modelo la produjo
    "Nota", "Originalidad",
    "Respuesta",      # en 'respuesta': lo que escribió el alumno
    "EvaluacionIA",   # en 'evaluacion': lo que devolvió el modelo
    "Detalle",        # en 'error': el mensaje
]

# Los dos flujos del curso
TESTS = "test"
TAREAS = "tarea"
