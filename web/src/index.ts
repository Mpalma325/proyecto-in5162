/**
 * API del sitio del curso.
 *
 * Para las personas (entran por Cloudflare Access):
 *   GET  /api/curso                     el código del curso (CURSO), para los títulos
 *   GET  /api/semestres                 qué semestres hay y cuál es el activo
 *   POST /api/semestres                 crear un semestre desde la plantilla o activarlo
 *   GET  /api/panel/:semestre           las filas de la reportería
 *   GET  /api/archivos/:semestre        qué archivos tiene (?prefijo=carpeta/)
 *   GET  /api/archivo/:semestre/:ruta   bajar uno (?descargar para guardarlo)
 *   PUT  /api/archivo/:semestre/:ruta   escribir uno, solo los de EDITABLES
 *   GET  /api/historial/:semestre       quién cambió qué archivo y cuándo (?ruta=)
 *   GET  /api/version/:id               la versión que había antes de esa edición
 *   GET|PUT /api/parametros             modelo, temperatura, escala de notas, grupos
 *   POST /api/trabajos                  pedir un trabajo: evaluar, enviar, tutoría...
 *   GET  /api/trabajos?semestre=X       los últimos trabajos de un semestre
 *   GET  /api/consumo/:semestre         lo que gastó en la API cada trabajo
 *   GET  /api/trabajos/:id              estado y salida de un trabajo
 *   POST /api/trabajos/:id/cancelar     detenerlo (antes de empezar, o entre un alumno y otro)
 *
 * Para el motor (Cloud Run), con su propio token:
 *   GET  /api/motor/archivos/:semestre        qué archivos tiene el semestre en R2
 *   GET  /api/motor/archivo/:semestre/:ruta   bajar uno
 *   PUT  /api/motor/archivo/:semestre/:ruta   subir uno
 *   GET  /api/motor/trabajos/:id              qué hay que ejecutar
 *   POST /api/motor/trabajos/:id              ir informando salida y estado
 *   POST /api/subir/:semestre                 reemplazar el panel de la reportería
 *
 * Todo lo demás son archivos de public/, que Cloudflare sirve sin pasar por acá.
 *
 * Tres credenciales, cada una con lo mínimo:
 *   - las personas pasan por Cloudflare Access; acá solo se verifica que pasaron.
 *   - el motor usa TOKEN_MOTOR para leer y escribir archivos y trabajos. No sirve
 *     para ver la reportería ni para pedir trabajos.
 *   - el Worker usa TOKEN_WEB para avisarle al motor que hay un trabajo nuevo.
 * El Worker nunca ve la clave de OpenAI ni la del correo: viven solo en el motor.
 */

import { correoVerificado } from "./acceso";

export interface Env {
  DB: D1Database;
  ASSETS: Fetcher;
  ARCHIVOS: R2Bucket;
  ACCESO: string;
  ACCESO_EQUIPO?: string;
  ACCESO_AUD?: string;
  MOTOR_URL: string;
  TOKEN_MOTOR?: string;
  TOKEN_WEB?: string;
  /** El código del curso, como "IN5162". */
  CURSO?: string;
}

// En el mismo orden que las claves de reportes.panel() en Python: es el orden
// de las columnas del CSV que se descarga, y tiene que coincidir con Streamlit.
const COLUMNAS = [
  "Correo", "Nombre", "Grupo", "EnRoster", "Item", "Enviado", "EnvioRegistrado",
  "Respondio", "Nota", "NotaTexto", "Originalidad", "Modelo", "FechaEnvio",
  "FechaRespuesta", "Respuesta", "EvaluacionIA",
] as const;

// Columnas que en Python son booleanas y en D1 quedan como 0/1.
const BOOLEANAS = new Set(["EnRoster", "Enviado", "EnvioRegistrado", "Respondio"]);

// Los flujos que se pueden pedir desde la página. Los argumentos los valida el
// motor, que es quien arma el comando; acá solo se filtra el nombre.
const FLUJOS = new Set([
  "tests.enviar", "tests.evaluar", "tests.resumen", "tests.tutoria", "tests.chequeo", "tests.experimento",
  "datos.panel", "datos.ajustar", "datos.sabana",
  "tareas.chequeo", "tareas.generar", "tareas.enviar", "tareas.recolectar", "tareas.corregir",
  "tareas.segunda",
]);

// Los parámetros que se pueden cambiar desde la página, con su validación.
// Las credenciales no están: viven solo en el motor, nunca pasan por el sitio.
// Precios de la API por modelo, en US$ por millón de tokens: {"modelo": [entrada, salida]}.
// Los escribe quien administra el curso; el sitio solo multiplica.
function preciosValidos(v: string): boolean {
  if (v.length > 4000) return false;
  try {
    const o = JSON.parse(v);
    return Boolean(o) && typeof o === "object" && !Array.isArray(o) && Object.entries(o).every(([m, p]) =>
      /^[A-Za-z0-9._:-]{2,60}$/.test(m) && Array.isArray(p) && p.length === 2
      && p.every((x) => typeof x === "number" && x >= 0 && x < 10000));
  } catch {
    return false;
  }
}

const PARAMETROS: Record<string, (v: string) => boolean> = {
  MODELO: (v) => /^[A-Za-z0-9._:-]{2,60}$/.test(v),
  TEMPERATURA: (v) => /^\d+(\.\d+)?$/.test(v) && Number(v) >= 0 && Number(v) <= 2,
  MAX_TOKENS: (v) => /^\d+$/.test(v) && Number(v) >= 200 && Number(v) <= 32000,
  // Los mismos rangos que tenía el formulario de Streamlit.
  NOTA_MIN: (v) => /^\d+(\.\d+)?$/.test(v) && Number(v) >= 1 && Number(v) <= 6.9,
  NOTA_MAX: (v) => /^\d+(\.\d+)?$/.test(v) && Number(v) > 1 && Number(v) <= 10,
  TAREA_DEFAULT: (v) => /^T\d{1,2}$/.test(v),
  GRUPO_CONTROL_TRATAMIENTO: (v) => v === "true" || v === "false",
  GRUPO_SEED: (v) => /^\d{1,5}$/.test(v),
  PRECIOS_API: (v) => preciosValidos(v),
};

// Material del curso que el modelo usa como contexto (modulos/tareas/contexto.py).
// Es lo único que se puede borrar desde la página.
const CONTEXTO = /^tareas\/data\/clases\/[^/]{1,200}\.(html|md|txt|R|r|py)$/;

// Qué archivos del semestre puede escribir una persona desde la página: lo
// mismo que se edita hoy en Streamlit. El resto solo lo escriben los trabajos.
const EDITABLES = [
  /^alumnos\.csv$/,
  /^tests_semanales\/data\/preguntas\.csv$/,
  /^tareas\/data\/alumnos\.csv$/,
  /^(tests_semanales|tareas)\/prompts\/[A-Za-z0-9_\-]+\.md$/,
  // Las entregas: el HTML de cada grupo y, si venía, el .Rmd con el mismo nombre.
  // Y la asignación de preguntas elegida a mano en el chequeo de Tareas.
  /^tareas\/data\/entregas\/(T\d{1,2})\/asignacion_\1\.csv$/,
  /^tareas\/data\/entregas\/T\d{1,2}\/[^/]{1,200}\.(html|Rmd)$/,
  // El contexto del curso para el modelo: clases renderizadas, apuntes, código.
  CONTEXTO,
];
const editable = (ruta: string) => EDITABLES.some((r) => r.test(ruta));

// Un semestre se llama como las carpetas: "2026-2". Se valida para que el id
// no pueda usarse para inyectar nada.
// Empieza con letra o número: así "." y ".." no pasan (colapsarían la ruta en
// el motor), ni "_template", que solo el motor puede tocar (idMotor).
const ID_VALIDO = /^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$/;
const idMotor = (s: string) => ID_VALIDO.test(s) || s === "_template";
// Una ruta dentro del semestre: sin "..", sin barra inicial, sin caracteres raros.
// Los nombres de las entregas de U-Cursos traen de todo: comas ("T1-Contreras,
// Del Pino.html"), acentos escritos como carácter aparte y hasta restos de una
// mala decodificación ("Cofre╠ü"). Se aceptan tal cual, porque el CSV de feedback
// los nombra así. Lo que no pasa: "..", barra inicial o doble, caracteres de
// control y los que Windows no admite en un nombre (para poder bajar el respaldo).
const RUTA_VALIDA = /^(?!.*\.\.)(?!\/)(?!.*\/\/)[^\u0000-\u001f\u007f\\:*?"<>|]{1,300}$/u;

function json(datos: unknown, estado = 200): Response {
  return new Response(JSON.stringify(datos), {
    status: estado,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

function error(estado: number, mensaje: string): Response {
  return json({ error: mensaje }, estado);
}

const ahora = () => new Date().toISOString();

// ---------------------------------------------------------------- acceso

/**
 * El correo de la persona que hizo la petición, o null.
 *
 * Solo cuenta el token firmado de Cloudflare Access (ver acceso.ts). Si Access
 * no está configurado, o falta ACCESO_EQUIPO o ACCESO_AUD, nadie es persona y
 * no se entregan datos. "abierto" existe solo para desarrollo local.
 */
async function persona(req: Request, env: Env): Promise<string | null> {
  if (env.ACCESO === "abierto") return req.headers.get("Cf-Access-Authenticated-User-Email") || "local";
  return correoVerificado(req.headers.get("Cf-Access-Jwt-Assertion"),
    { equipo: env.ACCESO_EQUIPO || "", aud: env.ACCESO_AUD || "" });
}

/** Comparación en tiempo constante, para que el token no se pueda adivinar midiendo. */
function mismoToken(a: string, b: string): boolean {
  const ea = new TextEncoder().encode(a);
  const eb = new TextEncoder().encode(b);
  if (ea.length !== eb.length) return false;
  let diferencia = 0;
  for (let i = 0; i < ea.length; i++) diferencia |= ea[i] ^ eb[i];
  return diferencia === 0;
}

function esMotor(req: Request, env: Env): boolean {
  if (!env.TOKEN_MOTOR) return false;
  const recibido = (req.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
  return mismoToken(recibido, env.TOKEN_MOTOR);
}

// ---------------------------------------------------------------- reportería

async function listarSemestres(env: Env): Promise<Response> {
  const { results } = await env.DB.prepare(
    "SELECT id, activo, filas, actualizado FROM semestres ORDER BY id",
  ).all();
  return json(results);
}

async function leerPanel(env: Env, semestre: string): Promise<Response> {
  const { results } = await env.DB.prepare(
    `SELECT ${COLUMNAS.join(", ")} FROM panel WHERE semestre = ?`,
  ).bind(semestre).all<Record<string, unknown>>();
  // Se devuelven con los mismos tipos que produce Python, para que
  // agregaciones.py reciba exactamente lo que recibiría en Streamlit.
  const filas = results.map((f) => {
    const fila: Record<string, unknown> = { ...f };
    for (const c of BOOLEANAS) fila[c] = Boolean(fila[c]);
    return fila;
  });
  return json(filas);
}

interface Subida {
  activo?: boolean;
  filas: Record<string, unknown>[];
}

async function subirPanel(req: Request, env: Env, semestre: string): Promise<Response> {
  let cuerpo: Subida;
  try {
    cuerpo = await req.json<Subida>();
  } catch {
    return error(400, "El cuerpo no es JSON válido.");
  }
  if (!Array.isArray(cuerpo.filas)) return error(400, "Falta la lista 'filas'.");

  const insertar = env.DB.prepare(
    `INSERT INTO panel (semestre, ${COLUMNAS.join(", ")})
     VALUES (?, ${COLUMNAS.map(() => "?").join(", ")})`,
  );
  const valor = (f: Record<string, unknown>, c: string) => {
    const v = f[c];
    if (BOOLEANAS.has(c)) return v ? 1 : 0;
    return v === undefined ? null : v;
  };

  // Se reemplaza el semestre completo en una sola transacción: o queda la
  // versión nueva entera, o queda la anterior. Nunca una mezcla.
  // Si la subida no dice nada del semestre activo (el motor, después de un
  // trabajo), se conserva lo que había. Solo el equipo que opera lo cambia.
  const tocaActivo = typeof cuerpo.activo === "boolean";
  const sentencias: D1PreparedStatement[] = [
    env.DB.prepare("DELETE FROM panel WHERE semestre = ?").bind(semestre),
    ...cuerpo.filas.map((f) => insertar.bind(semestre, ...COLUMNAS.map((c) => valor(f, c)))),
    env.DB.prepare(
      `INSERT INTO semestres (id, activo, filas, actualizado) VALUES (?, ?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET filas = excluded.filas, actualizado = excluded.actualizado
                                     ${tocaActivo ? ", activo = excluded.activo" : ""}`,
    ).bind(semestre, cuerpo.activo ? 1 : 0, cuerpo.filas.length, ahora()),
  ];
  if (cuerpo.activo === true) {
    // Solo un semestre puede ser el activo.
    sentencias.push(env.DB.prepare("UPDATE semestres SET activo = 0 WHERE id <> ?").bind(semestre));
  }
  await env.DB.batch(sentencias);
  return json({ semestre, filas: cuerpo.filas.length });
}

// ---------------------------------------------------------------- archivos (motor)

const clave = (semestre: string, ruta: string) => `semestres/${semestre}/${ruta}`;

async function listarArchivos(env: Env, semestre: string): Promise<Response> {
  const prefijo = `semestres/${semestre}/`;
  const archivos: { ruta: string; bytes: number; etag: string; subido: string }[] = [];
  let cursor: string | undefined;
  do {
    const pagina = await env.ARCHIVOS.list({ prefix: prefijo, cursor, limit: 1000 });
    for (const o of pagina.objects) {
      archivos.push({ ruta: o.key.slice(prefijo.length), bytes: o.size, etag: o.etag,
        subido: o.uploaded.toISOString() });
    }
    cursor = pagina.truncated ? pagina.cursor : undefined;
  } while (cursor);
  return json(archivos);
}

async function bajarArchivo(env: Env, semestre: string, ruta: string): Promise<Response> {
  const objeto = await env.ARCHIVOS.get(clave(semestre, ruta));
  if (!objeto) return error(404, "No existe ese archivo.");
  // Las entregas son HTML de los alumnos: se sirven como descarga y, si un
  // navegador igual intentara mostrarlas, sin poder correr nada en el sitio.
  return new Response(objeto.body, { headers: {
    "content-type": "application/octet-stream", "x-content-type-options": "nosniff",
    "content-security-policy": "sandbox",
  } });
}

/**
 * Escribe un archivo del semestre, guardando antes la versión que había.
 *
 * Todas las escrituras pasan por acá, las de la página y las del motor. Si un
 * trabajo deja mal notas.csv, o alguien borra filas de la lista de alumnos, la
 * versión anterior queda en historial/ y la edición anotada en `ediciones`.
 */
async function subirArchivo(req: Request, env: Env, semestre: string, ruta: string,
  quien: string): Promise<Response> {
  const cuerpo = await req.arrayBuffer();
  const actual = await env.ARCHIVOS.get(clave(semestre, ruta));
  // Escritura condicional: If-Match con el etag de la versión que se leyó, o
  // If-None-Match: * para un archivo nuevo. Si en la nube cambió mientras
  // tanto, no se pisa: 409, y quien escribía se entera.
  const siCoincide = (req.headers.get("If-Match") || "").replace(/"/g, "");
  if (siCoincide && (!actual || actual.etag !== siCoincide)) {
    return error(409, "El archivo cambió en la nube desde que se leyó. Vuelve a cargarlo.");
  }
  if (req.headers.get("If-None-Match") === "*" && actual) {
    return error(409, "El archivo ya existe en la nube.");
  }
  const t = ahora();
  let versionAnterior: string | null = null;
  if (actual) {
    versionAnterior = `historial/${semestre}/${ruta}/${t}`;
    await env.ARCHIVOS.put(versionAnterior, actual.body);
  }
  // onlyIf repite la condición en el mismo acto de escribir, por si otro
  // escribió entre el get de arriba y este put.
  const escrito = await env.ARCHIVOS.put(clave(semestre, ruta), cuerpo,
    actual ? { onlyIf: { etagMatches: actual.etag } } : undefined);
  if (!escrito) return error(409, "El archivo cambió en la nube mientras se guardaba. Vuelve a intentarlo.");
  await env.DB.prepare(
    `INSERT INTO ediciones (semestre, ruta, quien, cuando, bytes_antes, bytes_despues, version_anterior)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  ).bind(semestre, ruta, quien, t, actual ? actual.size : null, cuerpo.byteLength, versionAnterior).run();
  return json({ ruta, bytes: cuerpo.byteLength });
}

/** Borra un archivo, dejando antes su última versión en el historial. */
async function borrarArchivo(env: Env, semestre: string, ruta: string, quien: string): Promise<Response> {
  const actual = await env.ARCHIVOS.get(clave(semestre, ruta));
  if (!actual) return error(404, "No existe ese archivo.");
  const t = ahora();
  const versionAnterior = `historial/${semestre}/${ruta}/${t}`;
  await env.ARCHIVOS.put(versionAnterior, actual.body);
  await env.ARCHIVOS.delete(clave(semestre, ruta));
  await env.DB.prepare(
    `INSERT INTO ediciones (semestre, ruta, quien, cuando, bytes_antes, bytes_despues, version_anterior)
     VALUES (?, ?, ?, ?, ?, 0, ?)`,
  ).bind(semestre, ruta, quien, t, actual.size, versionAnterior).run();
  return json({ ruta, borrado: true });
}

/** Quién escribe desde el motor: "trabajo <id>" o "subida desde el PC". Solo texto simple. */
function origenMotor(req: Request): string {
  const o = (req.headers.get("X-In5162-Origen") || "motor").slice(0, 80);
  return /^[\p{L}\p{N} ._:@-]+$/u.test(o) ? o : "motor";
}

async function listarEdiciones(env: Env, semestre: string, ruta: string): Promise<Response> {
  const { results } = await env.DB.prepare(
    `SELECT id, ruta, quien, cuando, bytes_antes, bytes_despues, version_anterior IS NOT NULL AS hay_anterior
     FROM ediciones WHERE semestre = ? AND (? = '' OR ruta = ?) ORDER BY cuando DESC LIMIT 300`,
  ).bind(semestre, ruta, ruta).all();
  return json(results);
}

/** La versión que había antes de una edición, para bajarla. Se pide por id: nada de rutas. */
async function versionAnterior(env: Env, id: number): Promise<Response> {
  const e = await env.DB.prepare("SELECT ruta, cuando, version_anterior FROM ediciones WHERE id = ?")
    .bind(id).first<{ ruta: string; cuando: string; version_anterior: string | null }>();
  if (!e?.version_anterior) return error(404, "Esa edición no tiene versión anterior.");
  const objeto = await env.ARCHIVOS.get(e.version_anterior);
  if (!objeto) return error(404, "No encontré la versión anterior.");
  const [base, ext] = (e.ruta.split("/").pop() || "archivo").split(/\.(?=[^.]+$)/);
  const nombre = `${base}_antes_de_${e.cuando.slice(0, 16).replace(/[:T]/g, "-")}${ext ? `.${ext}` : ""}`;
  return new Response(objeto.body, { headers: {
    "content-type": "application/octet-stream", "content-disposition": `attachment; filename="${nombre}"`,
  } });
}

// ---------------------------------------------------------------- trabajos

interface PedidoTrabajo {
  semestre: string;
  flujo: string;
  argumentos?: Record<string, unknown>;
}

async function pedirTrabajo(req: Request, env: Env, quien: string): Promise<Response> {
  let p: PedidoTrabajo;
  try {
    p = await req.json<PedidoTrabajo>();
  } catch {
    return error(400, "El cuerpo no es JSON válido.");
  }
  if (!p.semestre || !ID_VALIDO.test(p.semestre)) return error(400, "Semestre inválido.");
  if (!FLUJOS.has(p.flujo)) return error(400, `Flujo desconocido: ${p.flujo}`);
  const args = p.argumentos && typeof p.argumentos === "object" ? p.argumentos : {};
  // Salvo que se pida explícitamente lo contrario, todo trabajo es de prueba.
  return json({ id: await crearTrabajo(env, p.semestre, p.flujo, args, quien) }, 201);
}

/** Registra el trabajo y le avisa al motor. Lo usan la página y el cron. */
async function crearTrabajo(env: Env, semestre: string, flujo: string,
                            args: Record<string, unknown>, quien: string): Promise<string> {
  const prueba = args.prueba !== false;
  args.prueba = prueba;

  const id = crypto.randomUUID();
  const t = ahora();
  await env.DB.prepare(
    `INSERT INTO trabajos (id, semestre, flujo, argumentos, prueba, estado, pedido_por, creado, actualizado)
     VALUES (?, ?, ?, ?, ?, 'pendiente', ?, ?, ?)`,
  ).bind(id, semestre, flujo, JSON.stringify(args), prueba ? 1 : 0, quien, t, t).run();

  // Se le avisa al motor, que lo pone en su cola y responde enseguida. Si no
  // contesta, el trabajo queda marcado como fallido con el motivo, en vez de
  // quedar "pendiente" para siempre.
  try {
    const r = await fetch(`${env.MOTOR_URL.replace(/\/$/, "")}/trabajos`, {
      method: "POST",
      headers: { "content-type": "application/json", Authorization: `Bearer ${env.TOKEN_WEB || ""}` },
      body: JSON.stringify({ id }),
    });
    if (!r.ok) throw new Error(`el motor respondió ${r.status}: ${(await r.text()).slice(0, 200)}`);
  } catch (e) {
    await env.DB.prepare(
      "UPDATE trabajos SET estado = 'fallido', salida = ?, actualizado = ? WHERE id = ?",
    ).bind(`No pude avisarle al motor: ${(e as Error).message}\n`, ahora(), id).run();
  }
  return id;
}

// Lo que corre solo, todos los días: responder las dudas sobre las correcciones,
// de verdad (manda correos), en el semestre activo. El cron de wrangler.toml va
// en UTC y Chile cambia de horario, así que se agenda a las dos horas posibles y
// acá se deja pasar solo la que en Santiago son las 18.
const HORA_RESPONDER_DUDAS = 18;

async function programado(env: Env, cuando: number): Promise<void> {
  const hora = Number(new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Santiago", hour: "numeric", hourCycle: "h23",
  }).format(new Date(cuando)));
  if (hora !== HORA_RESPONDER_DUDAS) return;
  const activo = await env.DB.prepare("SELECT id FROM semestres WHERE activo = 1 LIMIT 1").first<{ id: string }>();
  if (!activo) return;
  await crearTrabajo(env, activo.id, "tests.tutoria", { prueba: false }, `programado (${HORA_RESPONDER_DUDAS}:00)`);
}

// Detener un trabajo. Si no empezó, queda "cancelado" y el motor ya no lo toma
// (solo toma los "pendiente"). Si está corriendo, queda "cancelando": el motor lo
// ve en su próxima vuelta y lo para entre un alumno y otro (motor/trabajo.py).
async function cancelarTrabajo(env: Env, id: string, quien: string): Promise<Response> {
  const t = ahora();
  const antes = await env.DB.prepare(
    `UPDATE trabajos SET estado = 'cancelado', salida = salida || ?, actualizado = ?
     WHERE id = ? AND estado = 'pendiente'`,
  ).bind(`⊘ ${quien} lo canceló antes de que empezara.\n`, t, id).run();
  if (antes.meta.changes) return json({ estado: "cancelado" });
  const durante = await env.DB.prepare(
    `UPDATE trabajos SET estado = 'cancelando', salida = salida || ?, actualizado = ?
     WHERE id = ? AND estado = 'corriendo'`,
  ).bind(`\n⊘ ${quien} pidió detenerlo: para antes del alumno siguiente.\n`, t, id).run();
  if (durante.meta.changes) return json({ estado: "cancelando" });
  const existe = await env.DB.prepare("SELECT estado FROM trabajos WHERE id = ?").bind(id).first();
  return existe ? error(409, `El trabajo ya está ${existe.estado}.`) : error(404, "No existe ese trabajo.");
}

async function verTrabajo(env: Env, id: string): Promise<Response> {
  const t = await env.DB.prepare("SELECT * FROM trabajos WHERE id = ?").bind(id).first();
  if (!t) return error(404, "No existe ese trabajo.");
  return json({ ...t, argumentos: JSON.parse(String(t.argumentos || "{}")) });
}

/**
 * Lo que gastó en la API cada trabajo del semestre que llamó al modelo. Los
 * scripts imprimen al terminar una línea "Consumo de API (modelo): …"
 * (modulos/ia/cliente.py); acá se devuelven solo esas líneas, sin el resto de
 * la salida, y la página las suma con los precios (public/consumo.js).
 */
async function consumoDelSemestre(env: Env, semestre: string): Promise<Response> {
  const { results } = await env.DB.prepare(
    `SELECT id, flujo, argumentos, prueba, estado, pedido_por, creado, salida
     FROM trabajos WHERE semestre = ? AND salida LIKE '%Consumo de API (%' ORDER BY creado DESC LIMIT 2000`,
  ).bind(semestre).all();
  return json(results.map((t) => ({
    id: t.id, flujo: t.flujo, argumentos: JSON.parse(String(t.argumentos || "{}")), prueba: t.prueba,
    estado: t.estado, pedido_por: t.pedido_por, creado: t.creado,
    lineas: String(t.salida || "").split("\n").filter((l) => l.startsWith("Consumo de API (")),
  })));
}

async function listarTrabajos(env: Env, semestre: string): Promise<Response> {
  const { results } = await env.DB.prepare(
    `SELECT id, flujo, argumentos, prueba, estado, codigo, pedido_por, creado, actualizado, salida
     FROM trabajos WHERE semestre = ? ORDER BY creado DESC LIMIT 30`,
  ).bind(semestre).all();
  // De la salida solo va el último avance ("@@progreso 3/24 respuestas", de
  // modulos/progreso.py), para la barra de cada fila; la salida entera es por trabajo.
  return json(results.map(({ salida, ...t }) => {
    const avances = [...String(salida || "").matchAll(/^@@progreso (\d+)\/(\d+)(?: (.*))?$/gm)];
    const ultimo = avances[avances.length - 1];
    return {
      ...t, argumentos: JSON.parse(String(t.argumentos || "{}")),
      progreso: ultimo ? { hechos: Number(ultimo[1]), total: Number(ultimo[2]), unidad: ultimo[3] || "" } : null,
    };
  }));
}

interface Avance {
  salida?: string;
  estado?: string;
  codigo?: number;
}

const ESTADOS = new Set(["corriendo", "terminado", "fallido", "cancelado"]);

async function informarAvance(req: Request, env: Env, id: string): Promise<Response> {
  const a = await req.json<Avance>();
  if (a.estado && !ESTADOS.has(a.estado)) return error(400, "Estado inválido.");
  // Tomarlo ("corriendo") solo vale desde "pendiente", en una sola sentencia:
  // si la cola entrega el mismo trabajo dos veces a la vez, uno solo lo toma.
  // Y un trabajo terminado, fallido o cancelado no se reabre. Uno "cancelando"
  // sigue informando hasta que el motor lo cierra.
  const permitido = a.estado === "corriendo" ? "estado = 'pendiente'"
    : "estado IN ('pendiente', 'corriendo', 'cancelando')";
  // La salida se va agregando al final, así la página la ve crecer.
  const r = await env.DB.prepare(
    `UPDATE trabajos SET salida = salida || ?, estado = COALESCE(?, estado),
                         codigo = COALESCE(?, codigo), actualizado = ?
     WHERE id = ? AND ${permitido}`,
  ).bind(a.salida || "", a.estado ?? null, a.codigo ?? null, ahora(), id).run();
  if (!r.meta.changes) {
    const existe = await env.DB.prepare("SELECT estado FROM trabajos WHERE id = ?").bind(id).first();
    return existe ? error(409, `El trabajo ya está ${existe.estado}.`) : error(404, "No existe ese trabajo.");
  }
  return json({ ok: true });
}

// ---------------------------------------------------------------- parámetros

async function leerParametros(env: Env): Promise<Response> {
  const { results } = await env.DB.prepare("SELECT clave, valor, actualizado, por FROM parametros").all();
  return json(results);
}

async function guardarParametros(req: Request, env: Env, quien: string): Promise<Response> {
  const datos = await req.json<Record<string, string>>();
  const malos = Object.entries(datos).filter(([k, v]) => !PARAMETROS[k] || !PARAMETROS[k](String(v)));
  if (malos.length) return error(400, `Parámetros inválidos: ${malos.map(([k]) => k).join(", ")}`);
  if (datos.NOTA_MIN && datos.NOTA_MAX && Number(datos.NOTA_MIN) >= Number(datos.NOTA_MAX)) {
    return error(400, "La nota mínima tiene que ser menor que la máxima.");
  }
  const t = ahora();
  await env.DB.batch(Object.entries(datos).map(([k, v]) => env.DB.prepare(
    `INSERT INTO parametros (clave, valor, actualizado, por) VALUES (?, ?, ?, ?)
     ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor, actualizado = excluded.actualizado,
                                      por = excluded.por`,
  ).bind(k, String(v), t, quien)));
  return json({ guardados: Object.keys(datos) });
}

// ---------------------------------------------------------------- semestres

/** Crea un semestre copiando la plantilla, o cambia cuál es el activo. */
async function cambiarSemestre(req: Request, env: Env): Promise<Response> {
  const { id, crear, activo } = await req.json<{ id: string; crear?: boolean; activo?: boolean }>();
  if (!id || !ID_VALIDO.test(id) || id.startsWith("_")) return error(400, "Nombre de semestre inválido.");
  if (crear) {
    const ya = await env.ARCHIVOS.list({ prefix: `semestres/${id}/`, limit: 1 });
    if (ya.objects.length) return error(409, `El semestre ${id} ya existe.`);
    // Igual que en el PC: se copia siempre desde la plantilla, nunca desde el
    // semestre activo, para no arrastrar datos de otro curso.
    const plantilla = "semestres/_template/";
    let copiados = 0;
    let cursor: string | undefined;
    do {
      const pagina = await env.ARCHIVOS.list({ prefix: plantilla, cursor, limit: 1000 });
      for (const o of pagina.objects) {
        const obj = await env.ARCHIVOS.get(o.key);
        if (!obj) continue;
        await env.ARCHIVOS.put(`semestres/${id}/${o.key.slice(plantilla.length)}`, obj.body);
        copiados++;
      }
      cursor = pagina.truncated ? pagina.cursor : undefined;
    } while (cursor);
    if (!copiados) return error(500, "No encontré la plantilla de semestre en R2.");
    await env.DB.prepare(
      "INSERT OR IGNORE INTO semestres (id, activo, filas, actualizado) VALUES (?, 0, 0, ?)",
    ).bind(id, ahora()).run();
  }
  if (activo) {
    const existe = await env.DB.prepare("SELECT 1 FROM semestres WHERE id = ?").bind(id).first();
    if (!existe) return error(404, `No existe el semestre ${id}.`);
    await env.DB.batch([
      env.DB.prepare("UPDATE semestres SET activo = 0"),
      env.DB.prepare("UPDATE semestres SET activo = 1 WHERE id = ?").bind(id),
    ]);
  }
  return json({ id, creado: Boolean(crear), activo: Boolean(activo) });
}

// ---------------------------------------------------------------- rutas

export default {
  async scheduled(evento: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(programado(env, evento.scheduledTime));
  },
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(req);

    try {
      const partes = url.pathname.split("/").filter(Boolean).map(decodeURIComponent);
      // --- motor
      if (partes[1] === "motor" || partes[1] === "subir") {
        if (!esMotor(req, env)) return error(401, "Token de motor inválido.");
        const semestre = partes[2] || "";
        if (partes[1] === "subir" && req.method === "POST") {
          if (!ID_VALIDO.test(semestre)) return error(400, "Semestre inválido.");
          return await subirPanel(req, env, semestre);
        }
        if (partes[2] === "parametros" && req.method === "GET") return await leerParametros(env);
        if (partes[2] === "trabajos" && partes[3]) {
          if (req.method === "GET") return await verTrabajo(env, partes[3]);
          if (req.method === "POST") return await informarAvance(req, env, partes[3]);
        }
        if (partes[2] === "archivos" && partes[3] && req.method === "GET") {
          if (!idMotor(partes[3])) return error(400, "Semestre inválido.");
          return await listarArchivos(env, partes[3]);
        }
        if (partes[2] === "archivo" && partes[3]) {
          const sem = partes[3];
          const ruta = partes.slice(4).join("/");
          if (!idMotor(sem) || !RUTA_VALIDA.test(ruta)) return error(400, "Ruta inválida.");
          if (req.method === "GET") return await bajarArchivo(env, sem, ruta);
          if (req.method === "PUT") return await subirArchivo(req, env, sem, ruta, origenMotor(req));
        }
        return error(404, "No existe esa ruta.");
      }

      // --- personas
      const quien = await persona(req, env);
      if (!quien) return error(403, "Acceso no autenticado. Este sitio requiere Cloudflare Access.");
      // Una página ajena abierta por alguien con sesión podría pedir un trabajo
      // a su nombre (CSRF): el navegador manda la cookie de Access igual. Toda
      // escritura tiene que venir de este mismo sitio, que el navegador declara
      // en Origin y la página ajena no puede falsificar.
      if (req.method !== "GET" && req.method !== "HEAD" && req.headers.get("Origin") !== url.origin) {
        return error(403, "Pedido rechazado: no viene de esta página.");
      }

      if (partes[1] === "curso" && req.method === "GET") return json({ curso: env.CURSO || "IN5162" });
      if (partes[1] === "semestres" && req.method === "GET") return await listarSemestres(env);
      if (partes[1] === "semestres" && req.method === "POST") return await cambiarSemestre(req, env);
      if (partes[1] === "parametros") {
        if (req.method === "GET") return await leerParametros(env);
        if (req.method === "PUT") return await guardarParametros(req, env, quien);
      }
      // Listar archivos de una carpeta del semestre (prompts, entregas, feedback).
      if (partes[1] === "archivos" && partes[2] && req.method === "GET") {
        if (!ID_VALIDO.test(partes[2])) return error(400, "Semestre inválido.");
        const prefijo = url.searchParams.get("prefijo") || "";
        if (prefijo && !RUTA_VALIDA.test(prefijo)) return error(400, "Prefijo inválido.");
        const todos = await (await listarArchivos(env, partes[2])).json<{ ruta: string }[]>();
        return json(todos.filter((a) => a.ruta.startsWith(prefijo)));
      }
      if (partes[1] === "consumo" && partes[2] && req.method === "GET") {
        if (!ID_VALIDO.test(partes[2])) return error(400, "Semestre inválido.");
        return await consumoDelSemestre(env, partes[2]);
      }
      if (partes[1] === "panel" && partes[2] && req.method === "GET") {
        if (!ID_VALIDO.test(partes[2])) return error(400, "Semestre inválido.");
        return await leerPanel(env, partes[2]);
      }
      // Bajar un archivo del semestre, como el resumen semanal que genera un
      // trabajo. Solo lectura: las personas no escriben archivos por acá.
      if (partes[1] === "archivo" && partes[2] && req.method === "GET") {
        const ruta = partes.slice(3).join("/");
        if (!ID_VALIDO.test(partes[2]) || !RUTA_VALIDA.test(ruta)) return error(400, "Ruta inválida.");
        const r = await bajarArchivo(env, partes[2], ruta);
        if (r.ok && url.searchParams.has("descargar")) {
          r.headers.set("content-disposition", `attachment; filename="${ruta.split("/").pop()}"`);
        }
        return r;
      }
      // Escribir un archivo: solo los que se editan hoy en Streamlit (EDITABLES).
      if (partes[1] === "archivo" && partes[2] && req.method === "PUT") {
        const ruta = partes.slice(3).join("/");
        if (!ID_VALIDO.test(partes[2]) || !RUTA_VALIDA.test(ruta)) return error(400, "Ruta inválida.");
        if (!editable(ruta)) return error(403, "Ese archivo no se edita desde la página.");
        // Una entrega ya subida no se reemplaza: igual que en Streamlit, se omite.
        if (/^tareas\/data\/entregas\/.*\.(html|Rmd)$/.test(ruta) && await env.ARCHIVOS.head(clave(partes[2], ruta))) {
          return error(409, "Esa entrega ya existe.");
        }
        return await subirArchivo(req, env, partes[2], ruta, quien);
      }
      // Borrar: solo el contexto del curso. El resto de los archivos no se borra desde la página.
      if (partes[1] === "archivo" && partes[2] && req.method === "DELETE") {
        const ruta = partes.slice(3).join("/");
        if (!ID_VALIDO.test(partes[2]) || !RUTA_VALIDA.test(ruta)) return error(400, "Ruta inválida.");
        if (!CONTEXTO.test(ruta)) return error(403, "Ese archivo no se borra desde la página.");
        return await borrarArchivo(env, partes[2], ruta, quien);
      }
      // Historial de ediciones de un semestre (o de un archivo) y sus versiones anteriores.
      if (partes[1] === "historial" && partes[2] && req.method === "GET") {
        if (!ID_VALIDO.test(partes[2])) return error(400, "Semestre inválido.");
        const ruta = url.searchParams.get("ruta") || "";
        if (ruta && !RUTA_VALIDA.test(ruta)) return error(400, "Ruta inválida.");
        return await listarEdiciones(env, partes[2], ruta);
      }
      if (partes[1] === "version" && /^\d{1,12}$/.test(partes[2] || "") && req.method === "GET") {
        return await versionAnterior(env, Number(partes[2]));
      }
      if (partes[1] === "trabajos") {
        if (req.method === "POST" && !partes[2]) return await pedirTrabajo(req, env, quien);
        if (req.method === "POST" && partes[2] && partes[3] === "cancelar" && !partes[4]) {
          return await cancelarTrabajo(env, partes[2], quien);
        }
        if (req.method === "GET" && partes[2]) return await verTrabajo(env, partes[2]);
        if (req.method === "GET") {
          const sem = url.searchParams.get("semestre") || "";
          if (!ID_VALIDO.test(sem)) return error(400, "Semestre inválido.");
          return await listarTrabajos(env, sem);
        }
      }
      return error(404, "No existe esa ruta.");
    } catch (e) {
      if (e instanceof URIError) return error(400, "Ruta inválida.");
      return error(500, `Error interno: ${(e as Error).message}`);
    }
  },
} satisfies ExportedHandler<Env>;
