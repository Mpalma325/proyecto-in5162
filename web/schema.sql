-- Tablas del sitio. Por ahora una copia de lo que calcula el PC: la fuente de
-- verdad sigue siendo semestres/<id>/ en el equipo que opera el curso.

CREATE TABLE IF NOT EXISTS semestres (
  id          TEXT PRIMARY KEY,
  activo      INTEGER NOT NULL DEFAULT 0,  -- el que opera los envíos
  filas       INTEGER NOT NULL DEFAULT 0,
  actualizado TEXT                          -- cuándo lo subió el agente
);

-- Una fila por (alumno, ítem): la salida de modulos.datos.reportes.panel().
-- Los nombres de columna son los mismos que usa Python, para que la página
-- le pase las filas tal cual a agregaciones.py.
CREATE TABLE IF NOT EXISTS panel (
  semestre        TEXT NOT NULL,
  Correo          TEXT NOT NULL,
  Item            TEXT NOT NULL,
  Nombre          TEXT,
  Grupo           TEXT,
  EnRoster        INTEGER,
  Enviado         INTEGER,
  EnvioRegistrado INTEGER,
  Respondio       INTEGER,
  Nota            REAL,
  NotaTexto       TEXT,
  Originalidad    TEXT,
  Modelo          TEXT,
  FechaEnvio      TEXT,
  FechaRespuesta  TEXT,
  Respuesta       TEXT,
  EvaluacionIA    TEXT,
  PRIMARY KEY (semestre, Correo, Item)
);

-- Trabajos pedidos desde la página: evaluar, enviar, tutoría... Los ejecuta el
-- motor (Cloud Run) y va escribiendo acá la salida, que la página muestra en vivo.
CREATE TABLE IF NOT EXISTS trabajos (
  id          TEXT PRIMARY KEY,
  semestre    TEXT NOT NULL,
  flujo       TEXT NOT NULL,             -- "tests.evaluar", "tests.enviar", ...
  argumentos  TEXT NOT NULL,             -- JSON: {"semana": 4, "prueba": true}
  prueba      INTEGER NOT NULL DEFAULT 1, -- 1 = no manda correos
  estado      TEXT NOT NULL,             -- pendiente | corriendo | terminado | fallido
  salida      TEXT NOT NULL DEFAULT '',  -- lo que va imprimiendo el script
  codigo      INTEGER,                   -- código de salida del script
  pedido_por  TEXT,                      -- correo de quien lo pidió (Cloudflare Access)
  creado      TEXT NOT NULL,
  actualizado TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS trabajos_por_semestre ON trabajos (semestre, creado);

-- Parámetros de la revisión que se editan desde la página: modelo, temperatura,
-- escala de notas, grupos. El motor los lee en cada trabajo y se los pasa al
-- script como variables de entorno, que config.py toma antes que el .env.
-- Las credenciales NO van acá: viven solo en el motor (Secret Manager).
CREATE TABLE IF NOT EXISTS parametros (
  clave       TEXT PRIMARY KEY,
  valor       TEXT NOT NULL,
  actualizado TEXT NOT NULL,
  por         TEXT
);

-- Cada vez que se reemplaza o crea un archivo del semestre: quién, cuándo y
-- dónde quedó la versión anterior (en R2, bajo historial/, fuera de la carpeta
-- del semestre para que el motor no la baje en cada trabajo). Sirve para
-- deshacer un error y para saber quién cambió la lista de alumnos o un prompt.
CREATE TABLE IF NOT EXISTS ediciones (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  semestre         TEXT NOT NULL,
  ruta             TEXT NOT NULL,
  quien            TEXT NOT NULL,     -- correo de la persona, o "trabajo <id>", o "subida desde el PC"
  cuando           TEXT NOT NULL,
  bytes_antes      INTEGER,           -- NULL si el archivo no existía
  bytes_despues    INTEGER NOT NULL,
  version_anterior TEXT               -- clave en R2 de la copia; NULL si no había nada
);
CREATE INDEX IF NOT EXISTS ediciones_por_semestre ON ediciones (semestre, cuando);
