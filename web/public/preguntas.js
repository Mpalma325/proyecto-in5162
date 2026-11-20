// Las preguntas de los tests, una instancia a la vez.
//
// preguntas.csv tiene una fila por instancia y, por cada grupo, hasta tres
// preguntas con su pauta. Editarlo entero en una grilla obliga a buscar la fila
// y a leer párrafos en celdas angostas. Acá se elige la instancia, se ven sus
// preguntas como las va a recibir el alumno, y al guardar se reescribe solo esa
// fila: el resto del archivo queda igual, byte a byte (csv.js respeta su formato).
//
// Dos formatos, que se distinguen por la columna del id (modulos/tests/preguntas.py):
//   Semana     2026-2 y antes. «Semana N», todas confirmadas. Se ve y se edita como siempre.
//   Instancia  semestres nuevos. Un id que el docente no ve, más Tipo y Numero
//              («Control 2»), Estado (borrador o confirmada), Envio y Cierre
//              (ISO con la zona de Santiago). Al confirmar se programan el envío
//              y la evaluación (confirmarInstancia). Revision (auto o revisar)
//              es el interruptor «Revisar las correcciones antes de enviarlas»;
//              vacía, manda configuracion.json (modoInstancia). Se puede cambiar
//              en cualquier momento y vale para lo que se corrija desde ahí.
// En el código, `numero` es siempre el id; el número visible es `numeroTipo`.

import { api, caja, centrarSeleccion, conDetalle, confirmar, el, idDe, normalizar, pedirTrabajo, textoProgramado,
  urlTrabajos } from "./comun.js";
import { escribirCsv, leerCsv } from "./csv.js";
import {
  AUTO, AYUDA_REVISION, cargarConfiguracion, modoInstancia, REVISAR, ROTULO_REVISION,
} from "./configuracion.js";
import { ARCHIVO as ARCHIVO_ESCALA, leerEscala, POR_DEFECTO, rango } from "./escala.js";

/**
 * Qué pasa al cierre de una instancia confirmada, según su modo de revisión
 * (modoInstancia). `cuando` es «vie 14/11 10:00». Sin saber el modo (no se
 * pudo leer), lo dice en general.
 */
export function textoAlCierre(modo, cuando) {
  if (modo === AUTO) return `se evalúa ${cuando}, al cierre, con el feedback por correo.`;
  if (modo === REVISAR) {
    return `se corrige ${cuando}, al cierre; las correcciones quedan esperando tu revisión en Tests › Revisar y el `
      + "feedback no sale hasta que lo apruebes.";
  }
  return `se corrige ${cuando}, al cierre; el feedback sale solo o espera tu revisión, según lo que diga `
    + "«Revisar las correcciones antes de enviarlas» en esta instancia.";
}

export const RUTA = "tests_semanales/data/preguntas.csv";
const PLANTILLA_CORREO = "tests_semanales/prompts/correo_pregunta.md";
const GRUPOS = ["control", "tratamiento"];
const MAX_PREGUNTAS = 3;

const titulo = (g) => g[0].toUpperCase() + g.slice(1);
const columna = (grupo, i, pauta) => `${titulo(grupo)} ${pauta ? "Pauta " : ""}P${i}`;
const COLUMNAS = ["Semana", "Tema", "Fecha de Entrega",
  ...GRUPOS.flatMap((g) => [1, 2, 3].flatMap((i) => [columna(g, i, false), columna(g, i, true)]))];
const COLUMNAS_INSTANCIA = ["Instancia", "Tipo", "Numero", "Estado", "Envio", "Cierre"];
/** El modo de revisión de cada instancia. Opcional: un archivo sin la columna la recibe al guardar un modo. */
const COLUMNA_REVISION = "Revision";
/** La cabecera de un preguntas.csv nuevo, la misma de la plantilla (semestres/_template). */
export const CABECERA_NUEVA = [...COLUMNAS_INSTANCIA, COLUMNA_REVISION, "Tema", "Fecha de Entrega",
  ...GRUPOS.flatMap((g) => [false, true].flatMap((pauta) => [1, 2, 3].map((i) => columna(g, i, pauta))))];
/** Los tipos que se sugieren al crear una instancia; se puede escribir otro. */
export const TIPOS = ["Control", "Test", "Evaluación", "Instancia"];
const TIPO_POR_DEFECTO = "Instancia";
const ID = /^[1-9]\d{0,2}$/;
const lleno = (s) => String(s ?? "").trim() !== "";
/** Un preguntas.csv nuevo, con la cabecera y sin filas. */
export const archivoVacio = () => ({ columnas: [...CABECERA_NUEVA], filas: [] });

// ---------------------------------------------------------------- el archivo, sin pantalla

/** "Instancia", "Semana" o null: la columna del id. Con las dos, null (el archivo no se puede usar). */
export function columnaId(datos) {
  const [i, s] = ["Instancia", "Semana"].map((c) => datos.columnas.includes(c));
  return i && s ? null : i ? "Instancia" : s ? "Semana" : null;
}

/** Si el archivo es del formato antiguo (columna Semana): se ve y se comporta como siempre. */
export const esLegado = (datos) => columnaId(datos) === "Semana";

/** Las columnas que el editor necesita y el archivo no tiene. */
export function columnasFaltantes(datos) {
  const tiene = (c) => datos.columnas.includes(c);
  if (tiene("Semana") && tiene("Instancia")) return ["solo una de Semana o Instancia, no las dos"];
  if (!tiene("Instancia")) return COLUMNAS.filter((c) => !tiene(c));
  return [...COLUMNAS_INSTANCIA, ...COLUMNAS.slice(1)].filter((c) => !tiene(c));
}

function numeroDe(datos, fila) {
  const c = columnaId(datos);
  const t = c ? String(fila[datos.columnas.indexOf(c)] ?? "").trim() : "";
  return ID.test(t) ? Number(t) : null;
}

/** Los ids del archivo, en orden y sin repetir (de una fila repetida vale la primera, como en Python). */
const idsDe = (datos) => [...new Set(datos.filas.map((f) => numeroDe(datos, f)).filter((n) => n !== null))]
  .sort((a, b) => a - b);

/** Las instancias del archivo, en orden: [{ numero, nombre, tema, fecha, estado?, envio?, cierre?, avisos }]. */
export function semanasDe(datos) {
  return idsDe(datos).map((n) => {
    const s = leerSemana(datos, n);
    return { ...s, preguntas: undefined, nombre: nombreDe(s), avisos: avisosDe(s, true) };
  });
}

/** Lo que ve el docente: «Control 2», o «Semana 4» en el formato antiguo. */
export const nombreDe = (s) => (s.tipo ? `${s.tipo} ${s.numeroTipo}` : `Semana ${s.numero}`);

/** El asunto del correo de la pregunta, como lo arma modulos/tests/preguntas.py (asunto). */
export function asuntoDe(s) {
  if (!s.tipo) return `Evaluación de Progreso Individual Módulo ${s.numero}: ${s.tema.trim()}`;
  return lleno(s.tema) ? `${nombreDe(s)}: ${s.tema.trim()}` : nombreDe(s);
}

const estadoDeTexto = (t) => (["", "confirmada"].includes(String(t ?? "").trim().toLowerCase()) ? "confirmada" : "borrador");

/**
 * Una semana como se edita: tema, fecha y sus preguntas. Cada pregunta trae el
 * enunciado y la pauta de los dos grupos, y `igual` si los dos reciben lo
 * mismo. Si Tratamiento está entero vacío, el envío le manda lo de Control
 * (preguntas.py), así que esas preguntas también cuentan como iguales.
 */
export function leerSemana(datos, numero) {
  const fila = datos.filas.find((f) => numeroDe(datos, f) === numero);
  if (!fila) return null;
  const v = (c) => fila[datos.columnas.indexOf(c)] ?? "";
  const sinTratamiento = [1, 2, 3].every((i) => !lleno(v(columna("tratamiento", i, false)))
    && !lleno(v(columna("tratamiento", i, true))));
  const preguntas = [];
  for (let i = 1; i <= MAX_PREGUNTAS; i++) {
    const control = { texto: v(columna("control", i, false)), pauta: v(columna("control", i, true)) };
    const tratamiento = sinTratamiento ? { ...control }
      : { texto: v(columna("tratamiento", i, false)), pauta: v(columna("tratamiento", i, true)) };
    if (![control.texto, control.pauta, tratamiento.texto, tratamiento.pauta].some(lleno)) continue;
    const igual = control.texto === tratamiento.texto && control.pauta === tratamiento.pauta;
    preguntas.push({ control, tratamiento, igual });
  }
  const s = { numero, tema: v("Tema"), fecha: v("Fecha de Entrega"), preguntas };
  if (esLegado(datos)) return s;
  const n = String(v("Numero")).trim();
  return { ...s, tipo: String(v("Tipo")).trim() || TIPO_POR_DEFECTO, numeroTipo: ID.test(n) ? Number(n) : numero,
    estado: estadoDeTexto(v("Estado")), envio: String(v("Envio")).trim(), cierre: String(v("Cierre")).trim(),
    // Tal cual: vacío es «lo que diga configuracion.json» (modoInstancia).
    revision: String(v(COLUMNA_REVISION)).trim() };
}

/** El archivo con esa columna al final, si no la tenía (cada fila la recibe vacía). */
function conColumna(datos, columna) {
  if (datos.columnas.includes(columna)) return datos;
  return { ...datos, columnas: [...datos.columnas, columna], filas: datos.filas.map((f) => [...f, ""]) };
}

/** El modo de revisión, dicho para el registro de cambios y los mensajes. */
export const textoRevision = (modo) => (modo === AUTO ? "el feedback sale solo" : "se revisa antes de enviar");

/**
 * Qué cambió en una semana, en una frase para el registro: "Semana 11: cambió
 * la fecha de entrega y la pregunta 2 (control)". `antes` es null si es nueva.
 */
export function cambiosSemana(numero, antes, despues) {
  const quien = despues.tipo ? nombreDe(despues) : `Semana ${numero}`;
  if (!antes) return despues.tipo ? `${quien}: instancia nueva` : `Semana ${numero}: semana nueva`;
  const cambios = [];
  if (despues.tipo && nombreDe(antes) !== quien) cambios.push(`el nombre (antes ${nombreDe(antes)})`);
  if (antes.tema !== despues.tema) cambios.push("el tema");
  if (despues.tipo) {
    if (antes.envio !== despues.envio) cambios.push(`el envío (${textoFecha(despues.envio) || "vacío"})`);
    if (antes.cierre !== despues.cierre) cambios.push(`el cierre (${textoFecha(despues.cierre) || "vacío"})`);
  } else if (antes.fecha !== despues.fecha) cambios.push(`la fecha de entrega (${despues.fecha.trim() || "vacía"})`);
  const n = Math.max(antes.preguntas.length, despues.preguntas.length);
  for (let i = 0; i < n; i++) {
    const a = antes.preguntas[i];
    const d = despues.preguntas[i];
    if (!a) { cambios.push(`agregó la pregunta ${i + 1}`); continue; }
    if (!d) { cambios.push(`quitó la pregunta ${i + 1}`); continue; }
    const grupos = GRUPOS.filter((g) => a[g].texto !== d[g].texto || a[g].pauta !== d[g].pauta);
    if (!grupos.length) continue;
    const partes = [...new Set(grupos.flatMap((g) => [a[g].texto !== d[g].texto && "enunciado",
      a[g].pauta !== d[g].pauta && "pauta"]).filter(Boolean))].join(" y ");
    cambios.push(`la pregunta ${i + 1} (${partes}${d.igual ? "" : `, ${grupos.join(" y ")}`})`);
  }
  if (despues.tipo && (antes.revision || "") !== (despues.revision || "") && despues.revision) {
    cambios.push(`la revisión (ahora ${textoRevision(despues.revision)})`);
  }
  if (despues.tipo && antes.estado !== despues.estado) {
    cambios.push(despues.estado === "confirmada" ? "quedó confirmada" : "volvió a borrador");
  }
  if (!cambios.length) return `${quien}: sin cambios`;
  const lista = cambios.length > 1 ? `${cambios.slice(0, -1).join(", ")} y ${cambios[cambios.length - 1]}` : cambios[0];
  return `${quien}: cambió ${lista}`.replace(/cambió (agregó|quitó|quedó|volvió)/, "$1");
}

/**
 * El archivo con la fila de esa semana reemplazada; las demás filas no se tocan.
 * Las preguntas se escriben en orden (P1, P2...) y una pregunta "igual" se
 * copia a los dos grupos, que es lo que lee preguntas.py.
 */
export function escribirSemana(datos, numero, semana) {
  // Un archivo de antes del interruptor recibe la columna Revision cuando una instancia dice su modo.
  if (semana.tipo && lleno(semana.revision)) datos = conColumna(datos, COLUMNA_REVISION);
  const i = datos.filas.findIndex((f) => numeroDe(datos, f) === numero);
  if (i < 0) throw new Error(`No existe la semana ${numero} en el archivo.`);
  const fila = [...datos.filas[i]];
  const poner = (c, valor) => { fila[datos.columnas.indexOf(c)] = valor; };
  poner("Tema", semana.tema);
  // En el formato nuevo la fecha de entrega que lee el alumno sale del cierre.
  poner("Fecha de Entrega", semana.tipo && lleno(semana.cierre) ? textoFecha(semana.cierre) : semana.fecha);
  if (semana.tipo) {
    poner("Tipo", semana.tipo.trim());
    poner("Numero", String(semana.numeroTipo));
    poner("Estado", semana.estado);
    poner("Envio", semana.envio);
    poner("Cierre", semana.cierre);
    if (datos.columnas.includes(COLUMNA_REVISION)) poner(COLUMNA_REVISION, semana.revision ?? "");
  }
  const preguntas = semana.preguntas.filter((p) =>
    [p.control.texto, p.control.pauta, p.tratamiento.texto, p.tratamiento.pauta].some(lleno));
  for (let n = 1; n <= MAX_PREGUNTAS; n++) {
    const p = preguntas[n - 1];
    for (const g of GRUPOS) {
      const lado = p ? (p.igual ? p.control : p[g]) : { texto: "", pauta: "" };
      poner(columna(g, n, false), lado.texto);
      poner(columna(g, n, true), lado.pauta);
    }
  }
  const filas = [...datos.filas];
  filas[i] = fila;
  return { ...datos, filas };
}

/** El archivo sin esa instancia (solo se ofrece para borradores que no se han enviado). */
export function quitarInstancia(datos, numero) {
  return { ...datos, filas: datos.filas.filter((f) => numeroDe(datos, f) !== numero) };
}

const mismoTipo = (a, b) => normalizar(String(a).trim()) === normalizar(String(b).trim());

/**
 * El número visible que le toca a una instancia nueva de ese tipo: el mayor de
 * ese tipo más uno. `sin` deja fuera una instancia (la que está cambiando de tipo).
 * Los números no se reasignan: borrar «Control 1» no convierte a «Control 2» en 1.
 */
export function siguienteNumero(datos, tipo, sin = null) {
  const usados = idsDe(datos).filter((n) => n !== sin).map((n) => leerSemana(datos, n))
    .filter((s) => mismoTipo(s.tipo, tipo)).map((s) => s.numeroTipo);
  return usados.length ? Math.max(...usados) + 1 : 1;
}

/** El tipo con que se propone crear la siguiente: el de la última creada, o «Instancia». */
export function tipoPorDefecto(datos) {
  const ultima = idsDe(datos).at(-1);
  return ultima ? leerSemana(datos, ultima).tipo : TIPO_POR_DEFECTO;
}

/**
 * Cambiar el tipo de un borrador: toma el número siguiente de ese tipo, o el
 * suyo si vuelve al tipo con que está guardado.
 */
export function conTipo(datos, s, tipo) {
  const guardada = leerSemana(datos, s.numero);
  const numeroTipo = guardada && mismoTipo(guardada.tipo, tipo) ? guardada.numeroTipo : siguienteNumero(datos, tipo, s.numero);
  return { ...s, tipo, numeroTipo };
}

/**
 * Una instancia nueva, en borrador. El id es el mayor de preguntas.csv y de los
 * Item de tests de notas.csv, más uno: así una instancia borrada que se envió
 * nunca le pasa sus notas a otra. Si el archivo está vacío, se crea con la
 * cabecera nueva. Devuelve [datos, id].
 *
 * El modo de revisión es el de la última instancia creada (`respaldo` es el
 * de configuracion.json, para una que no dice el suyo); la primera del
 * semestre parte revisando.
 */
export function agregarInstancia(datos, { tipo = null, itemsNotas = [], respaldo = REVISAR } = {}) {
  const base = conColumna(datos && datos.columnas.some(lleno) ? datos : archivoVacio(), COLUMNA_REVISION);
  const tipoNuevo = String(tipo ?? tipoPorDefecto(base)).trim() || TIPO_POR_DEFECTO;
  const ids = [...idsDe(base), ...itemsNotas.map(Number).filter((n) => Number.isInteger(n) && n > 0)];
  const numero = ids.length ? Math.max(...ids) + 1 : 1;
  const previa = idsDe(base).at(-1);
  const valores = { Instancia: String(numero), Tipo: tipoNuevo, Numero: String(siguienteNumero(base, tipoNuevo)),
    Estado: "borrador",
    [COLUMNA_REVISION]: previa ? modoInstancia(leerSemana(base, previa).revision, respaldo || REVISAR) : REVISAR };
  const fila = base.columnas.map((c) => valores[c] ?? "");
  let ultima = -1;
  base.filas.forEach((f, i) => { if (numeroDe(base, f) !== null) ultima = i; });
  const filas = [...base.filas];
  filas.splice(ultima + 1, 0, fila);
  return [{ ...base, filas }, numero];
}

/** El archivo con una semana nueva y vacía, la siguiente a la última. Devuelve [datos, número]. */
export function agregarSemana(datos) {
  const numeros = datos.filas.map((f) => numeroDe(datos, f)).filter((n) => n !== null);
  const numero = numeros.length ? Math.max(...numeros) + 1 : 1;
  const fila = datos.columnas.map((c) => (c === "Semana" ? String(numero) : ""));
  // Después de la última semana, no después de alguna fila en blanco del final.
  let ultima = -1;
  datos.filas.forEach((f, i) => { if (numeroDe(datos, f) !== null) ultima = i; });
  const filas = [...datos.filas];
  filas.splice(ultima + 1, 0, fila);
  return [{ ...datos, filas }, numero];
}

// Para buscar: sin tildes, sin mayúsculas y con los saltos de línea como un espacio.
const paraBuscar = (s) => normalizar(s).replace(/\s+/g, " ").trim();

/**
 * Las semanas que calzan con una búsqueda: [{ numero, coincidencias }], cada
 * coincidencia { pregunta, grupos, texto }. Se busca en el enunciado y el tema;
 * "7" o "semana 7" va directo a esa semana, si existe. `grupo` ("control" o
 * "tratamiento") busca solo en lo que recibe ese grupo; vacío, en los dos.
 */
export function buscarPreguntas(datos, consulta, grupo = "") {
  const q = paraBuscar(consulta);
  const semanas = semanasDe(datos);
  if (!q) return semanas.map((s) => ({ numero: s.numero, coincidencias: [] }));
  // En el formato nuevo el número no es el id: «control 2» va directo a esa, si existe.
  const porNombre = semanas.find((s) => s.tipo && paraBuscar(s.nombre) === q);
  if (porNombre) return [{ numero: porNombre.numero, coincidencias: [] }];
  const n = esLegado(datos) && q.match(/^(?:semana|sem\.?)?\s*(\d+)$/);
  if (n && semanas.some((s) => s.numero === Number(n[1]))) return [{ numero: Number(n[1]), coincidencias: [] }];
  return semanas.flatMap(({ numero }) => {
    const s = leerSemana(datos, numero);
    const coincidencias = s.preguntas.flatMap((p, i) => {
      const grupos = (grupo ? [grupo] : GRUPOS).filter((g) => paraBuscar(p[g].texto).includes(q));
      return grupos.length ? [{ pregunta: i + 1, grupos, texto: p[grupos[0]].texto }] : [];
    });
    return coincidencias.length || paraBuscar(s.tema).includes(q) ? [{ numero, coincidencias }] : [];
  });
}

/**
 * El pedazo de `texto` donde aparece la búsqueda, para mostrarlo bajo la
 * semana: { antes, encontrado, despues }, o null si no aparece.
 */
export function extracto(texto, consulta, alrededor = 30) {
  const q = paraBuscar(consulta);
  // El texto normalizado letra a letra, recordando de qué posición del original viene cada una.
  let plano = "";
  const origen = [];
  let pos = 0;
  for (const c of String(texto ?? "")) {
    const n = /\s/.test(c) ? " " : normalizar(c);
    if (!(n === " " && plano.endsWith(" "))) {
      plano += n;
      for (let k = 0; k < n.length; k++) origen.push(pos);
    }
    pos += c.length;
  }
  const i = q ? plano.indexOf(q) : -1;
  if (i < 0) return null;
  const desde = origen[i];
  const hasta = i + q.length < origen.length ? origen[i + q.length] : pos;
  const t = String(texto);
  const corto = (s) => s.replace(/\s+/g, " ");
  const inicio = Math.max(0, desde - alrededor);
  const fin = Math.min(t.length, hasta + alrededor);
  return {
    antes: `${inicio > 0 ? "…" : ""}${corto(t.slice(inicio, desde)).trimStart()}`,
    encontrado: corto(t.slice(desde, hasta)),
    despues: `${corto(t.slice(hasta, fin)).trimEnd()}${fin < t.length ? "…" : ""}`,
  };
}

/** Lo que conviene revisar antes de enviar. `corto` da las etiquetas de la lista de semanas. */
export function avisosDe(semana, corto = false) {
  const avisos = [];
  if (!semana.preguntas.length) {
    avisos.push(corto ? "sin preguntas" : semana.tipo ? "No tiene preguntas: no se puede enviar."
      : "La semana no tiene preguntas: no se puede enviar.");
    return avisos;
  }
  if (semana.tipo) {
    // La fecha de entrega sale del cierre; lo que falta se dice al confirmar.
    semana.preguntas.forEach((p, i) => avisos.push(...avisosDePregunta(p, i, corto)));
    return corto ? [...new Set(avisos)] : avisos;
  }
  if (!lleno(semana.fecha)) {
    avisos.push(corto ? "sin fecha"
      : "Falta la fecha de entrega: el correo diría «La fecha de entrega es:» y nada más.");
  }
  const dia = diaQueNoCalza(semana.fecha);
  if (dia) avisos.push(corto ? "el día no calza" : dia);
  semana.preguntas.forEach((p, i) => avisos.push(...avisosDePregunta(p, i, corto)));
  return corto ? [...new Set(avisos)] : avisos;
}

const DIAS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];

/**
 * Si la fecha nombra un día de la semana que no es el suyo ("lunes 13/06",
 * y el 13/06 cae sábado), el texto que lo explica; si no, null. Suele pasar
 * al copiar las fechas de otro semestre y cambiar solo el número.
 */
export function diaQueNoCalza(texto, hoy = new Date()) {
  const fecha = fechaEntrega(texto, hoy);
  if (!fecha) return null;
  const limpio = normalizar(String(texto));
  const nombrado = DIAS.findIndex((d) => new RegExp(`\\b${normalizar(d)}\\b`).test(limpio));
  if (nombrado < 0 || nombrado === fecha.getDay()) return null;
  const dma = `${String(fecha.getDate()).padStart(2, "0")}/${String(fecha.getMonth() + 1).padStart(2, "0")}`
    + `/${fecha.getFullYear()}`;
  return `La fecha dice ${DIAS[nombrado]}, pero el ${dma} es ${DIAS[fecha.getDay()]}.`;
}

/** Lo que le falta a una pregunta: enunciado vacío o sin pauta, en cada grupo que la recibe distinta. */
export function avisosDePregunta(p, i, corto = false) {
  const avisos = [];
  const lados = p.igual ? [["", p.control]] : GRUPOS.map((g) => [` (${titulo(g)})`, p[g]]);
  for (const [cual, lado] of lados) {
    if (!lleno(lado.texto)) {
      avisos.push(corto ? "pregunta vacía"
        : `La pregunta ${i + 1}${cual} está vacía: ese grupo recibiría una pregunta menos.`);
    } else if (!lleno(lado.pauta)) {
      avisos.push(corto ? "falta pauta"
        : `La pregunta ${i + 1}${cual} no tiene pauta: la IA corregiría sin saber qué se espera.`);
    }
  }
  return avisos;
}

/**
 * La fecha de entrega como fecha, si el texto la trae. Es texto libre, así
 * que se reconoce lo que se ha usado: "lunes 19/10/2026, 10:15", "Viernes
 * 05/06/2026", "13/06 10:15", "2026-03-15". Sin hora, el fin del día; sin año,
 * el de `hoy`. Si no se reconoce, null: la página muestra el texto tal cual.
 */
export function fechaEntrega(texto, hoy = new Date()) {
  const t = String(texto || "");
  let d, m, a;
  let x = t.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (x) {
    [a, m, d] = [Number(x[1]), Number(x[2]), Number(x[3])];
  } else if ((x = t.match(/(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?/))) {
    [d, m] = [Number(x[1]), Number(x[2])];
    a = x[3] ? Number(x[3]) : hoy.getFullYear();
    if (a < 100) a += 2000;
  } else {
    return null;
  }
  const h = t.match(/(\d{1,2}):(\d{2})/);
  const fecha = h ? new Date(a, m - 1, d, Number(h[1]), Number(h[2])) : new Date(a, m - 1, d, 23, 59);
  // 31/02 no existe: Date lo corre a marzo, y eso sería inventar una fecha.
  return Number.isNaN(fecha.getTime()) || fecha.getMonth() !== m - 1 ? null : fecha;
}

// ---------------------------------------------------------------- el correo, como lo arma enviar.py

const ESTILO_CITA = "border-left: 3px solid #ccc; margin: 10px 0; padding-left: 12px; color: #555;";

/** Igual que _construir_bloque_preguntas() de modulos/tests/enviar.py: «de la semana» solo en el formato antiguo. */
export function bloquePreguntas(preguntas, legado = true) {
  const de = legado ? " de la semana" : "";
  if (preguntas.length === 1) {
    return `<p>La pregunta${de} es:</p>\n<blockquote style="${ESTILO_CITA}">\n  ${preguntas[0]}\n</blockquote>`;
  }
  return [`<p>Las preguntas${de} son:</p>`,
    ...preguntas.map((p, i) => `<blockquote style="${ESTILO_CITA}">\n  ${i + 1}. ${p}\n</blockquote>`)].join("\n");
}

/**
 * El correo que recibe un alumno de ese grupo: { asunto, html }. `escala` es la
 * del semestre (escala.js), para {ESCALA}; sin ella, la de siempre (4,0 a 7,0).
 */
export function correoDe(plantilla, semana, grupo, nombre = "Ana", escala = POR_DEFECTO) {
  const preguntas = semana.preguntas.map((p) => (p.igual ? p.control : p[grupo]).texto.trim()).filter(lleno);
  // Como preguntas.py: en el formato nuevo manda el cierre, y la columna queda de respaldo.
  const fecha = (semana.tipo && textoFecha(semana.cierre)) || semana.fecha.trim();
  return {
    asunto: asuntoDe(semana),
    html: plantilla
      .replaceAll("{ESCALA}", rango(escala))
      .replaceAll("{NOMBRE}", nombre)
      .replaceAll("{TEMA}", semana.tema.trim())
      .replaceAll("{FECHA_ENTREGA}", fecha)
      .replaceAll("{BLOQUE_PREGUNTAS}", bloquePreguntas(preguntas, !semana.tipo))
      .replaceAll("{SEMANA}", String(semana.tipo ? semana.numeroTipo : semana.numero))
      .replaceAll("{TITULO}", nombreDe(semana)),
  };
}

// ---------------------------------------------------------------- fechas y horas de Santiago
// Envio y Cierre se guardan como ISO con la zona de Santiago ("2026-10-19T10:15:00-03:00"):
// el motor y la cola las leen como instantes, y la hora de pared queda escrita.

const ZONA = "America/Santiago";
const dos = (n) => String(n).padStart(2, "0");

/** Cuántos minutos hay que sumarle a UTC para tener la hora de Santiago en ese instante. */
function desfaseSantiago(ms) {
  const z = new Intl.DateTimeFormat("en-US", { timeZone: ZONA, timeZoneName: "longOffset" }).formatToParts(new Date(ms))
    .find((p) => p.type === "timeZoneName")?.value || "GMT";
  const m = z.match(/GMT([+-])(\d{1,2}):?(\d{2})?/);
  return m ? (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3] || 0)) : 0;
}
const textoDesfase = (min) => `${min < 0 ? "-" : "+"}${dos(Math.floor(Math.abs(min) / 60))}:${dos(Math.abs(min) % 60)}`;

/** "2026-10-19T10:15" (lo que da un <input type="datetime-local">, hora de Santiago) -> ISO con su zona. */
export function isoSantiago(local) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(String(local || ""));
  if (!m) return "";
  const pared = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]));
  // Dos vueltas: el desfase de esa hora de pared, no el de la misma hora en UTC.
  const desfase = desfaseSantiago(pared - desfaseSantiago(pared) * 60_000);
  return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:00${textoDesfase(desfase)}`;
}

/** Un ISO -> "2026-10-19T10:15" en hora de Santiago, para el <input type="datetime-local">. */
export function localSantiago(iso) {
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? "" : new Date(ms + desfaseSantiago(ms) * 60_000).toISOString().slice(0, 16);
}

/** Ahora, como ISO con la zona de Santiago y con segundos. */
export function isoAhora(ms = Date.now()) {
  const d = desfaseSantiago(ms);
  return `${new Date(ms + d * 60_000).toISOString().slice(0, 19)}${textoDesfase(d)}`;
}

const DIAS_SEMANA = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];

/**
 * "2026-10-19T10:15:00-03:00" -> "lunes 19/10/2026, 10:15", con la hora escrita
 * en el ISO. Es la fecha de entrega que lee el alumno; igual que texto_fecha() de
 * modulos/tests/preguntas.py, y fechaEntrega() la vuelve a leer.
 */
export function textoFecha(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(String(iso || "").trim());
  if (!m || Number.isNaN(Date.parse(iso))) return "";
  const dia = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]))).getUTCDay();
  return `${DIAS_SEMANA[dia]} ${m[3]}/${m[2]}/${m[1]}, ${Number(m[4])}:${m[5]}`;
}

// ---------------------------------------------------------------- confirmar y programar
// Una instancia nueva nace en borrador: se edita y se simula, pero no se envía.
// Al confirmarla se programan dos trabajos reales con a_las: el envío a la hora
// de Envio y la evaluación a la de Cierre (src/index.ts los deja esperando en la
// cola, o en D1 si faltan más de 29 días). Volver a borrador anula los dos, y
// el motor igual se niega a enviar un borrador (modulos/tests/enviar.py).

const DIA_MS = 864e5;
/** El mismo límite que PROGRAMAR_HASTA_DIAS en src/index.ts. */
export const PROGRAMAR_HASTA_DIAS = 200;
const FLUJOS_PROGRAMADOS = ["tests.enviar", "tests.evaluar"];

/**
 * De notas.csv: cuántos alumnos tienen Enviado en cada test (Map id -> n),
 * cuántas correcciones esperan al docente (Corregido sin Nota ni Descartada,
 * Map id -> n; lo mismo que «por revisar» en ciclo.js) y todos los Item de tests.
 */
export function enviosDeNotas(texto) {
  const enviados = new Map();
  const esperando = new Map();
  const items = new Set();
  if (!String(texto || "").trim()) return { enviados, esperando, items: [] };
  const { columnas, filas } = leerCsv(texto);
  const [iF, iI, iE, iC, iN, iD] = ["Flujo", "Item", "Enviado", "Corregido", "Nota", "Descartada"]
    .map((c) => columnas.indexOf(c));
  for (const f of filas) {
    const n = Number(String(f[iI] ?? "").trim());
    if (String(f[iF] ?? "").trim() !== "test" || !Number.isInteger(n) || n < 1) continue;
    items.add(n);
    if (lleno(f[iE])) enviados.set(n, (enviados.get(n) || 0) + 1);
    if (iC >= 0 && lleno(f[iC]) && !lleno(f[iN]) && !(iD >= 0 && lleno(f[iD]))) esperando.set(n, (esperando.get(n) || 0) + 1);
  }
  return { enviados, esperando, items: [...items] };
}

// ---------------------------------------------------------------- el modo de revisión de una instancia
// Un interruptor por instancia: encendido, las correcciones esperan al docente;
// apagado, salen solas. El evaluar programado al cierre lo lee al correr, así
// que cambiarlo después de confirmar (o de enviar) vale para lo que se corrija
// desde ese momento. Lo que ya espera en Revisar sigue esperando.

/** El archivo con el modo de esa instancia cambiado (y la columna Revision, si no la tenía). */
export function conRevision(datos, numero, modo) {
  const conCol = conColumna(datos, COLUMNA_REVISION);
  const i = conCol.filas.findIndex((f) => numeroDe(conCol, f) === numero);
  if (i < 0) throw new Error("Esa instancia no está en preguntas.csv.");
  const filas = [...conCol.filas];
  filas[i] = [...filas[i]];
  filas[i][conCol.columnas.indexOf(COLUMNA_REVISION)] = modo;
  return { ...conCol, filas };
}

/**
 * Lo que se pregunta antes de pasar una instancia a automático: desde ahora el
 * feedback sale sin que nadie lo vea, y lo que ya espera en Revisar no sale
 * solo. Pasar a revisar no pregunta nada (es lo seguro): devuelve null.
 */
export function textoCambioRevision(nombre, modo, esperando = 0) {
  if (modo !== AUTO) return null;
  const quedan = esperando === 1 ? "Queda 1 corrección esperando" : `Quedan ${esperando} correcciones esperando`;
  return `Desde ahora, cada corrección de ${nombre} le llega al alumno por correo apenas queda lista, sin que la `
    + "veas antes."
    + (esperando > 0 ? `\n\n${quedan} en Tests › Revisar. ${esperando === 1 ? "Esa no sale sola" : "Esas no salen solas"}: `
      + "apruébalas y envíalas desde ahí (está «Aprobar todas»)." : "")
    + "\n\n¿Dejar de revisar antes de enviar?";
}

/**
 * El interruptor, con su rótulo y la línea que dice qué pasa en cada
 * posición. `alCambiar(modo)` hace lo que haga falta (preguntar, guardar) y
 * devuelve false si no se hizo: el interruptor vuelve a donde estaba.
 */
export function interruptorRevision({ modo, alCambiar, deshabilitado = false }) {
  const casilla = el("input", { type: "checkbox", checked: modo !== AUTO, disabled: deshabilitado });
  casilla.addEventListener("change", async () => {
    const antes = !casilla.checked;
    casilla.disabled = true;
    let hecho = false;
    try {
      hecho = await alCambiar(casilla.checked ? REVISAR : AUTO) !== false;
    } finally {
      if (!hecho) casilla.checked = antes;
      casilla.disabled = deshabilitado;
    }
  });
  return el("div", { class: "interruptor-revision" },
    el("label", { class: "interruptor" }, casilla, ROTULO_REVISION),
    el("p", { class: "nota-pie" }, AYUDA_REVISION));
}

/**
 * Guarda el modo de una instancia en preguntas.csv: lee el archivo con su
 * etag, cambia esa celda y lo escribe con If-Match. Si alguien lo guardó
 * entretanto (409), relee y aplica el mismo cambio una vez más: solo toca la
 * celda de esa instancia, así que no pisa lo que cambió el otro. Devuelve el
 * texto guardado.
 */
export async function guardarRevision(semestre, numero, modo, nombre) {
  for (let intento = 0; ; intento++) {
    const r = await fetch(urlArchivo(semestre, RUTA), { cache: "no-store" });
    if (!r.ok) throw new Error(r.status === 404 ? "preguntas.csv no existe" : `${r.status} ${r.statusText}`);
    const etag = r.headers.get("etag");
    const texto = escribirCsv(conRevision(leerCsv(await r.text()), numero, modo));
    const w = await fetch(urlArchivo(semestre, RUTA), {
      method: "PUT", body: texto,
      headers: { "content-type": "text/csv; charset=utf-8", ...(etag ? { "if-match": etag } : {}),
        ...conDetalle(`${nombre}: ${textoRevision(modo)}`) },
    });
    if (w.ok) return texto;
    if (w.status !== 409 || intento >= 1) {
      const cuerpo = await w.json().catch(() => ({}));
      throw new Error(cuerpo.error || `${w.status} ${w.statusText}`);
    }
  }
}

/**
 * El interruptor de Tests (Evaluar y Revisar): pregunta si hace falta y guarda
 * apenas se aprieta. `esperando` = correcciones de esa instancia que esperan en
 * Revisar. `alGuardar(modo)` corre después de guardar; `mensaje` muestra el
 * resultado. Devuelve el nodo.
 */
export function interruptorDeInstancia({ semestre, numero, nombre, modo, esperando = 0, alGuardar, mensaje }) {
  return interruptorRevision({ modo, alCambiar: async (nuevo) => {
    const pregunta = textoCambioRevision(nombre, nuevo, typeof esperando === "function" ? esperando() : esperando);
    if (pregunta && !await confirmar(pregunta, "Dejar de revisar", "real")) return false;
    try {
      await guardarRevision(semestre, numero, nuevo, nombre);
    } catch (e) {
      mensaje?.replaceChildren(caja("aviso", `No pude guardarlo: ${e.message}`));
      return false;
    }
    mensaje?.replaceChildren(caja("exito", nuevo === AUTO
      ? `Guardado: en ${nombre} el feedback sale solo desde ahora.`
      : `Guardado: en ${nombre} las correcciones esperan tu revisión desde ahora.`));
    await alGuardar?.(nuevo);
    return true;
  } });
}

const deInstancia = (t, numero) => Number(idDe(t.argumentos || {})) === numero;

/** Los trabajos reales de esa instancia que esperan su hora (o su turno en la cola). */
export function programadosDe(trabajos, numero, flujos = FLUJOS_PROGRAMADOS) {
  return trabajos.filter((t) => flujos.includes(t.flujo) && !t.prueba && t.estado === "pendiente" && deInstancia(t, numero));
}

/** Si un envío real de esa instancia ya empezó o terminó: entonces ya salieron correos. */
export const envioEmpezado = (trabajos, numero) => trabajos.some((t) => t.flujo === "tests.enviar" && !t.prueba
  && ["corriendo", "cancelando", "terminado"].includes(t.estado) && deInstancia(t, numero));

/**
 * Lo que impide confirmar ([] si se puede). Con `enviarAhora` el envío es este
 * momento y no se le pide que esté en el futuro.
 */
export function problemasAlConfirmar(s, { ahora = Date.now(), enviarAhora = false } = {}) {
  const p = [];
  if (!s.preguntas.length) p.push("No tiene preguntas.");
  const envio = enviarAhora ? ahora : Date.parse(s.envio);
  const cierre = Date.parse(s.cierre);
  if (Number.isNaN(envio)) p.push("Falta la fecha y hora de envío.");
  if (Number.isNaN(cierre)) p.push("Falta la fecha y hora de cierre.");
  if (!enviarAhora && envio <= ahora) p.push("La hora de envío ya pasó: elige una futura, o «Confirmar y enviar ahora».");
  if (cierre <= envio) p.push("El cierre tiene que ser después del envío.");
  if (cierre > ahora + PROGRAMAR_HASTA_DIAS * DIA_MS) {
    p.push(`El cierre está a más de ${PROGRAMAR_HASTA_DIAS} días: confírmala más cerca de la fecha.`);
  }
  return p;
}

/** Lo que impide cambiar el cierre de una instancia ya confirmada ([] si se puede). */
export function problemasAlCambiarCierre(s, ahora = Date.now()) {
  const cierre = Date.parse(s.cierre);
  if (Number.isNaN(cierre)) return ["Falta la fecha y hora de cierre."];
  if (cierre <= ahora) return ["El cierre nuevo ya pasó: la evaluación se programa a esa hora."];
  if (cierre <= Date.parse(s.envio)) return ["El cierre tiene que ser después del envío."];
  if (cierre > ahora + PROGRAMAR_HASTA_DIAS * DIA_MS) return [`El cierre está a más de ${PROGRAMAR_HASTA_DIAS} días.`];
  return [];
}

/** Los dos trabajos reales que deja programados una instancia confirmada: [flujo, argumentos]. */
export const trabajosAlConfirmar = (s) => [
  ["tests.enviar", { instancia: s.numero, prueba: false, a_las: s.envio }],
  ["tests.evaluar", { instancia: s.numero, prueba: false, a_las: s.cierre }],
];

/**
 * Confirmar: guarda la fila como confirmada y programa el envío y la evaluación.
 * `d` = { guardar(instancia, detalle), pedir(flujo, argumentos) -> id, cancelar(id) }.
 * Si alguno no se pudo pedir, anula los que alcanzó a pedir, la deja en
 * borrador y levanta el error. Devuelve los ids de los dos trabajos.
 */
export async function confirmarInstancia(s, d) {
  const confirmada = { ...s, estado: "confirmada" };
  await d.guardar(confirmada, `${nombreDe(s)}: quedó confirmada; envío ${textoFecha(s.envio)}, cierre ${textoFecha(s.cierre)}`);
  const pedidos = [];
  try {
    for (const [flujo, argumentos] of trabajosAlConfirmar(confirmada)) pedidos.push(await d.pedir(flujo, argumentos));
  } catch (e) {
    for (const id of pedidos) await d.cancelar(id).catch(() => {});
    await d.guardar({ ...s, estado: "borrador" }, `${nombreDe(s)}: volvió a borrador (no se pudo programar)`);
    throw e;
  }
  return pedidos;
}

/**
 * Volver a borrador, solo si todavía no se envía. Guarda el estado primero
 * (así un envío que llegue a su hora entretanto encuentra el borrador y no
 * manda nada) y después anula los trabajos programados de la instancia.
 * `d` = { guardar, cancelar, trabajos() -> lista, enviados: número }.
 * Devuelve { cancelados, fallaron: [trabajos que no se pudieron anular] }.
 */
export async function volverABorrador(s, d) {
  const trabajos = await d.trabajos();
  if (d.enviados > 0 || envioEmpezado(trabajos, s.numero)) {
    throw new Error(`${nombreDe(s)} ya se envió: no puede volver a borrador.`);
  }
  await d.guardar({ ...s, estado: "borrador" }, `${nombreDe(s)}: volvió a borrador`);
  const fallaron = [];
  const pendientes = programadosDe(trabajos, s.numero);
  for (const t of pendientes) {
    try { await d.cancelar(t.id); } catch { fallaron.push(t); }
  }
  return { cancelados: pendientes.length - fallaron.length, fallaron };
}

/**
 * Cambió el cierre de una instancia confirmada (enviada o no): se programa la
 * evaluación a la hora nueva y después se anula la que esperaba la vieja. El
 * envío no se toca. Devuelve el id del trabajo nuevo.
 */
export async function reprogramarCierre(s, d) {
  const viejos = programadosDe(await d.trabajos(), s.numero, ["tests.evaluar"]);
  const id = await d.pedir("tests.evaluar", { instancia: s.numero, prueba: false, a_las: s.cierre });
  for (const t of viejos) await d.cancelar(t.id);
  return id;
}

/**
 * Para «Tabla completa»: lo que no se puede guardar porque toca una instancia
 * ya enviada ([] si nada). Una enviada no se borra, no vuelve a borrador, y su
 * Tipo, Numero y Tema quedan fijos: el asunto del feedback («Re: Control 2:
 * tema»), el reconocimiento de las respuestas y el hilo de Gmail dependen de
 * ellos. El formato antiguo no se revisa: se edita como siempre.
 */
export function cambiosProhibidos(antes, despues, enviados) {
  if (!antes?.columnas?.length || esLegado(antes)) return [];
  const problemas = [];
  for (const n of idsDe(antes)) {
    if (!(enviados.get(n) > 0)) continue;
    const a = leerSemana(antes, n);
    const d = columnaId(despues) === "Instancia" ? leerSemana(despues, n) : null;
    if (!d) { problemas.push(`${nombreDe(a)} ya se envió: no se puede quitar.`); continue; }
    if (nombreDe(d) !== nombreDe(a) || d.tema.trim() !== a.tema.trim()) {
      problemas.push(`${nombreDe(a)} ya se envió: su tipo, número y tema quedan fijos, porque el asunto del feedback y `
        + "el reconocimiento de las respuestas dependen de ellos.");
    }
    if (d.estado === "borrador" && a.estado !== "borrador") problemas.push(`${nombreDe(a)} ya se envió: no puede volver a borrador.`);
  }
  return [...problemas, ...nombresRepetidos(despues)];
}

/**
 * Dos instancias con el mismo Tipo y Número se llaman igual en la página y en
 * el asunto, y el alumno no distingue los correos. Lo mismo que avisa
 * modulos/tests/preguntas.py (_nombres_repetidos); acá no deja guardar.
 */
export function nombresRepetidos(datos) {
  if (!datos?.columnas?.length || columnaId(datos) !== "Instancia") return [];
  const vistos = new Map();
  const problemas = [];
  for (const n of idsDe(datos)) {
    const s = leerSemana(datos, n);
    const clave = `${s.tipo.split(/\s+/).join(" ").toLowerCase()}\u0000${s.numeroTipo}`;
    if (vistos.has(clave)) {
      problemas.push(`${s.tipo} ${s.numeroTipo} aparece dos veces (ids ${vistos.get(clave)} y ${n}): cambia el número `
        + "de una de las dos.");
    } else {
      vistos.set(clave, n);
    }
  }
  return problemas;
}

/** Lo que le pasa a la instancia, en pocas palabras, para la lista y el encabezado. */
export function estadoInstancia(s, enviados = 0) {
  if (enviados > 0) return { clase: "enviada", texto: `enviada a ${enviados}` };
  if (s.estado === "borrador") return { clase: "borrador", texto: "borrador" };
  const envio = new Date(s.envio);
  return { clase: "programada",
    texto: Number.isNaN(envio.getTime()) ? "confirmada" : `sale ${textoProgramado(envio)}` };
}

// ---------------------------------------------------------------- hablar con el sitio

const urlArchivo = (semestre, ruta) =>
  `/api/archivo/${encodeURIComponent(semestre)}/${ruta.split("/").map(encodeURIComponent).join("/")}`;

async function leerTexto(semestre, ruta) {
  const r = await fetch(urlArchivo(semestre, ruta), { cache: "no-store" });
  if (!r.ok) throw new Error(r.status === 404 ? "no existe" : `${r.status} ${r.statusText}`);
  return r.text();
}

async function etagDe(semestre) {
  const lista = await api(`/api/archivos/${encodeURIComponent(semestre)}`);
  return lista.find((a) => a.ruta === RUTA)?.etag ?? null;
}

// ---------------------------------------------------------------- pantalla

/** Un textarea que crece con su contenido, para no leer párrafos por una rendija. */
function areaTexto(valor, alCambiar, attrs = {}) {
  const t = el("textarea", { rows: "3", spellcheck: "true", ...attrs }, valor);
  const ajustar = () => { t.style.height = "auto"; t.style.height = `${t.scrollHeight + 2}px`; };
  t.addEventListener("input", () => { alCambiar(t.value); ajustar(); });
  requestAnimationFrame(ajustar);
  return t;
}

/**
 * El editor: la lista de semanas (o instancias) a la izquierda y la elegida a
 * la derecha. `alCambiarSemana(n)` avisa cuál se está viendo (para la URL),
 * `alCambiar(hayCambios)` si hay algo sin guardar, `alGuardar(destino)` corre
 * después de guardar y `alLeer({ legado })` dice en qué formato está el archivo.
 * En el formato nuevo cada instancia nace en borrador y se confirma desde aquí.
 */
export function editorPreguntas({ semestre, semana: inicial, usaGrupos = true,
  alCambiarSemana, alCambiar, alGuardar, alLeer } = {}) {
  const raiz = el("div", { class: "editor-preguntas" }, el("p", { class: "cargando" }, "Cargando las preguntas…"));
  let datos = null; // el archivo como se ve ahora
  let guardado = null; // el texto del archivo tal como está en la nube (null: todavía no existe)
  let etag = null;
  let actual = null; // id de la instancia elegida
  let borrador = null; // esa instancia, con lo que se ha editado
  let original = null; // la misma instancia al abrirla, para saber si hay cambios
  let plantilla = null; // correo_pregunta.md, para la vista previa
  let escalaSemestre = POR_DEFECTO; // escala_notas.json, para {ESCALA}
  let envios = { enviados: new Map(), esperando: new Map(), items: [] }; // de notas.csv
  let legado = true;
  // El modo de respaldo de configuracion.json, para las instancias sin Revision; null si no se pudo leer.
  let respaldo = null;
  const modoDe = (s) => modoInstancia(s.revision, respaldo);

  const hayCambios = () => borrador !== null && JSON.stringify(borrador) !== original;
  const avisarCambio = () => alCambiar?.(hayCambios());
  const enviadosDe = (n) => envios.enviados.get(n) || 0;
  // «La semana 4» o «Control 2»: cómo se nombra la elegida en los mensajes.
  const laElegida = () => (legado ? `La semana ${actual}` : nombreDe(borrador));
  // Sin archivo, o vacío: un semestre nuevo, que empieza en el formato nuevo.
  const releer = () => { datos = lleno(guardado) ? leerCsv(guardado) : archivoVacio(); };

  async function descartarSiHace() {
    if (!hayCambios()) return true;
    if (!await confirmar(`${laElegida()} tiene cambios sin guardar. ¿Descartarlos?`, "Descartar", "peligro")) {
      return false;
    }
    releer();
    return true;
  }

  function elegir(numero) {
    actual = numero;
    borrador = leerSemana(datos, numero);
    original = JSON.stringify(borrador);
    alCambiarSemana?.(numero);
    avisarCambio();
    dibujar();
  }

  /** Escribe el archivo con su etag; si alguien lo cambió entretanto, falla en vez de pisarlo. */
  async function guardarArchivo(nuevos, detalle) {
    const texto = escribirCsv(nuevos);
    await api(urlArchivo(semestre, RUTA), {
      method: "PUT", body: texto,
      headers: { "content-type": "text/csv; charset=utf-8", ...(etag ? { "if-match": etag } : { "if-none-match": "*" }),
        ...conDetalle(detalle) },
    });
    datos = leerCsv(texto);
    guardado = texto;
    etag = await etagDe(semestre);
  }

  // Lo que necesitan confirmar, volver a borrador y cambiar el cierre (confirmarInstancia y compañía).
  const sitio = {
    guardar: (s, detalle) => guardarArchivo(escribirSemana(datos, s.numero, s), detalle),
    pedir: (flujo, argumentos) => pedirTrabajo(semestre, flujo, argumentos),
    cancelar: (id) => api(`/api/trabajos/${encodeURIComponent(id)}/cancelar`, { method: "POST" }),
    // Los recientes (para ver si un envío ya está corriendo) más todos los
    // pendientes, sin la ventana del historial: los programados a 200 días
    // también se cancelan aunque la tutoría diaria haya llenado los 120 últimos.
    trabajos: async () => {
      const [recientes, pendientes] = await Promise.all([
        api(urlTrabajos(semestre, "tests.", 120)), api(urlTrabajos(semestre, "tests.", undefined, true))]);
      const ids = new Set(recientes.map((t) => t.id));
      return [...recientes, ...pendientes.filter((t) => !ids.has(t.id))];
    },
  };

  /** Después de una operación que guardó: la instancia vuelve a leerse del archivo. */
  function tras(mensajeExito, tipo = "exito") {
    borrador = leerSemana(datos, actual);
    original = JSON.stringify(borrador);
    dibujar();
    mensaje.replaceChildren(caja(tipo, mensajeExito));
    avisarCambio();
  }

  // ------------------------------------------------ buscar
  // Filtra la lista de semanas. Lo escrito se mantiene al elegir una semana.
  const buscador = el("input", { type: "search", placeholder: "Buscar…",
    "aria-label": "Buscar por enunciado, tema o número de semana" });
  const grupoBuscado = usaGrupos ? el("select", { "aria-label": "Buscar en el grupo" },
    el("option", { value: "" }, "Ambos grupos"), GRUPOS.map((g) => el("option", { value: g }, `Grupo ${g}`))) : null;
  const columna = el("div", { class: "columna-semanas" },
    el("div", { class: "buscar-preguntas", role: "search" }, buscador, grupoBuscado));
  // Solo se rehace la lista: el buscador no pierde el foco mientras se escribe.
  function pintarLista() {
    const nueva = listaSemanas();
    const vieja = columna.querySelector(":scope > .lista-semanas");
    if (vieja) vieja.replaceWith(nueva); else columna.append(nueva);
  }
  buscador.addEventListener("input", pintarLista);
  grupoBuscado?.addEventListener("change", pintarLista);

  /** Dónde apareció lo buscado, bajo el tema: "P2: …texto…". */
  function lineaHallada(c, consulta) {
    const x = c && extracto(c.texto, consulta);
    if (!x) return null;
    const cual = usaGrupos && !grupoBuscado.value && c.grupos.length === 1 ? ` ${titulo(c.grupos[0])}` : "";
    return el("span", { class: "extracto" }, `P${c.pregunta}${cual}: `, x.antes, el("mark", {}, x.encontrado), x.despues);
  }

  /** Una pregunta vacía, para empezar una instancia o semana nueva. */
  const preguntaVacia = () => ({ control: { texto: "", pauta: "" }, tratamiento: { texto: "", pauta: "" }, igual: true });

  // ------------------------------------------------ la lista de semanas
  function listaSemanas() {
    const consulta = buscador.value.trim();
    const hallados = consulta ? new Map(buscarPreguntas(datos, consulta, usaGrupos ? grupoBuscado.value : "control")
      .map((r) => [r.numero, r.coincidencias])) : null;
    const semanas = semanasDe(datos).filter((s) => !hallados || hallados.has(s.numero));
    const agregar = el("button", { class: "agregar-semana", type: "button", onclick: async () => {
      if (!await descartarSiHace()) return;
      const [nuevos, numero] = legado ? agregarSemana(datos) : agregarInstancia(datos, { itemsNotas: envios.items,
        respaldo: respaldo || REVISAR });
      datos = nuevos;
      actual = numero;
      borrador = { ...leerSemana(datos, numero), preguntas: [preguntaVacia()] };
      original = null; // una semana nueva no existe hasta guardarla
      alCambiarSemana?.(numero);
      avisarCambio();
      dibujar();
    } }, legado ? "+ Agregar semana" : "+ Nueva instancia");
    // En celular es una tira que se desliza: que se vea la semana elegida, no la 1.
    const lista = el("nav", { class: "lista-semanas", "aria-label": legado ? "Semanas" : "Instancias" },
      hallados && !semanas.length ? el("p", { class: "nota-pie sin-resultados" }, "Sin resultados.") : null,
      semanas.map((s) => {
        const estado = legado ? null : estadoInstancia(s, enviadosDe(s.numero));
        // Solo se marca la excepción: las que no se revisan antes de enviar.
        const automatica = !legado && modoDe(s) === AUTO;
        return el("button", {
          type: "button", class: "item-semana", "aria-current": s.numero === actual ? "true" : null,
          onclick: async () => { if (s.numero !== actual && await descartarSiHace()) elegir(s.numero); },
        },
        el("span", { class: "num-semana" }, s.nombre),
        el("span", { class: "tema-semana" }, lleno(s.tema) ? s.tema : "Sin tema"),
        lineaHallada(hallados?.get(s.numero)?.[0], consulta),
        estado || automatica || s.avisos.length ? el("span", { class: "marcas" },
          estado ? el("span", { class: `marca estado-instancia ${estado.clase}` }, estado.texto) : null,
          automatica ? el("span", { class: "marca" }, "feedback automático") : null,
          s.avisos.map((a) => el("span", { class: "marca" }, a))) : null);
      }),
      agregar);
    centrarSeleccion(lista);
    return lista;
  }

  // ------------------------------------------------ una variante: enunciado y pauta
  function variante(lado, etiqueta, numero) {
    const ids = `p${numero}-${etiqueta || "unica"}`;
    return el("div", { class: "variante" },
      etiqueta ? el("span", { class: `pildora ${etiqueta}` }, titulo(etiqueta)) : null,
      el("label", { class: "campo", for: `${ids}-texto` }, "Enunciado"),
      areaTexto(lado.texto, (v) => { lado.texto = v; cambio(); },
        { id: `${ids}-texto`, placeholder: "Pregunta" }),
      el("label", { class: "campo", for: `${ids}-pauta` }, "Pauta (solo la ve la IA)"),
      areaTexto(lado.pauta, (v) => { lado.pauta = v; cambio(); },
        { id: `${ids}-pauta`, class: "pauta", placeholder: "Lo que se espera en la respuesta" }));
  }

  function tarjetaPregunta(p, i) {
    const distinta = el("input", { type: "checkbox", checked: !p.igual });
    distinta.addEventListener("change", async () => {
      if (distinta.checked) {
        // Parten iguales y se edita lo que cambia.
        p.tratamiento = { ...p.control };
        p.igual = false;
      } else {
        const iguales = p.tratamiento.texto === p.control.texto && p.tratamiento.pauta === p.control.pauta;
        if (!iguales && !await confirmar("Tratamiento va a recibir lo mismo que Control y se pierde su texto. ¿Seguir?",
          "Dejar iguales", "peligro")) {
          distinta.checked = true;
          return;
        }
        p.tratamiento = { ...p.control };
        p.igual = true;
      }
      cambio();
      dibujar();
    });
    const quitar = el("button", { class: "enlace", type: "button", onclick: async () => {
      const tieneTexto = [p.control.texto, p.control.pauta, p.tratamiento.texto, p.tratamiento.pauta].some(lleno);
      if (tieneTexto && !await confirmar(`¿Quitar la pregunta ${i + 1}? Las siguientes se corren un lugar.`,
        "Quitar", "peligro")) return;
      borrador.preguntas.splice(i, 1);
      cambio();
      dibujar();
    } }, "Quitar");
    const separadas = usaGrupos && !p.igual;
    const avisosTarjeta = el("div", { class: "avisos-tarjeta" });
    avisosPorTarjeta.push({ nodo: avisosTarjeta, p, i });
    return el("section", { class: "tarjeta-pregunta" },
      el("header", {},
        el("h4", {}, `Pregunta ${i + 1}`),
        usaGrupos ? el("label", { class: "interruptor" }, distinta, "Distinta por grupo (control y tratamiento)") : null,
        quitar),
      separadas
        ? el("div", { class: "dos-variantes" }, variante(p.control, "control", i + 1),
          variante(p.tratamiento, "tratamiento", i + 1))
        : variante(p.control, "", i + 1),
      avisosTarjeta);
  }

  // ------------------------------------------------ vista previa del correo
  function vistaPrevia() {
    const contenido = el("div");
    const detalles = el("details", { class: "vista-previa" },
      el("summary", {}, "Vista previa del correo"), el("div", { class: "contenido" }, contenido));
    const mostrar = (grupo) => {
      const { asunto, html } = correoDe(plantilla, borrador, grupo, "Ana", escalaSemestre);
      const distintas = usaGrupos && borrador.preguntas.some((p) => !p.igual);
      contenido.replaceChildren(
        distintas ? el("div", { class: "chips" }, GRUPOS.map((g) => el("button", {
          type: "button", class: "chip", "aria-pressed": String(g === grupo), onclick: () => mostrar(g),
        }, `Como ${titulo(g)}`))) : "",
        el("p", { class: "asunto" }, el("span", { class: "tenue" }, "Asunto: "), asunto),
        // Sin permisos: el HTML del correo se muestra, pero no puede correr nada en el sitio.
        el("iframe", { class: "correo", sandbox: "", srcdoc: html,
          title: legado ? `Correo de la semana ${borrador.numero}` : `Correo de ${nombreDe(borrador)}` }));
    };
    detalles.addEventListener("toggle", async () => {
      if (!detalles.open) return;
      if (plantilla === null) {
        contenido.replaceChildren(el("p", { class: "cargando" }, "Cargando la plantilla del correo…"));
        try {
          plantilla = await leerTexto(semestre, PLANTILLA_CORREO);
          // {ESCALA} sale de escala_notas.json; sin el archivo, 4,0 a 7,0.
          escalaSemestre = leerEscala(await leerTexto(semestre, ARCHIVO_ESCALA).catch(() => null)).escala;
        } catch (e) {
          contenido.replaceChildren(caja("aviso", `No pude leer correo_pregunta.md: ${e.message}`));
          return;
        }
      }
      mostrar("control");
    });
    return detalles;
  }

  // ------------------------------------------------ la semana elegida
  const estadoGuardado = el("span", { class: "estado-guardado" });
  const avisos = el("div");
  // Los avisos van junto a lo que hay que arreglar, no todos al fondo. Se
  // rearman en cada dibujo de la semana.
  const avisoFecha = el("span", { class: "aviso-campo" });
  let avisosPorTarjeta = [];
  let campoFecha = null;
  function pintarAvisos() {
    const sinFecha = legado && borrador.preguntas.length > 0 && !lleno(borrador.fecha);
    avisoFecha.textContent = sinFecha ? "Falta la fecha: el correo diría «La fecha de entrega es:» y nada más." : "";
    campoFecha?.classList.toggle("falta", sinFecha);
    for (const { nodo, p, i } of avisosPorTarjeta) {
      nodo.replaceChildren(...avisosDePregunta(p, i).map((a) => el("p", { class: "aviso-campo" }, a)));
    }
    avisos.replaceChildren(borrador.preguntas.length ? ""
      : caja("aviso", legado ? "La semana no tiene preguntas: no se puede enviar." : "No tiene preguntas: no se puede enviar."));
  }
  const mensaje = el("div");
  const botonGuardar = el("button", { class: "primario", type: "button" });
  const botonDescartar = el("button", { class: "descarga", type: "button" }, "Descartar cambios");

  function cambio() {
    const hay = hayCambios();
    estadoGuardado.textContent = hay ? "Cambios sin guardar" : "Sin cambios";
    estadoGuardado.classList.toggle("pendiente", hay);
    botonGuardar.disabled = !hay;
    botonDescartar.hidden = !hay;
    pintarAvisos();
    mensaje.replaceChildren();
    avisarCambio();
  }

  botonDescartar.addEventListener("click", async () => {
    if (!await confirmar(legado ? `¿Descartar los cambios de la semana ${actual}?`
      : `¿Descartar los cambios de ${nombreDe(borrador)}?`, "Descartar", "peligro")) return;
    releer();
    const sigue = leerSemana(datos, actual) ? actual : semanasDe(datos)[0]?.numero ?? null;
    if (sigue === null) { borrador = null; dibujar(); return; }
    elegir(sigue);
  });

  botonGuardar.addEventListener("click", async () => {
    botonGuardar.disabled = true;
    const antes = original ? JSON.parse(original) : null;
    // Una instancia confirmada a la que le cambió el cierre: su evaluación se programa de nuevo.
    const cambiaCierre = !legado && antes && borrador.estado === "confirmada" && antes.cierre !== borrador.cierre;
    if (cambiaCierre) {
      const problemas = problemasAlCambiarCierre(borrador);
      if (problemas.length) {
        botonGuardar.disabled = false;
        mensaje.replaceChildren(caja("aviso", problemas.join(" ")));
        return;
      }
    }
    try {
      await guardarArchivo(escribirSemana(datos, actual, borrador), cambiosSemana(actual, antes, borrador));
      borrador = leerSemana(datos, actual);
      original = JSON.stringify(borrador);
      dibujar();
      mensaje.replaceChildren(caja("exito", legado ? `Semana ${actual} guardada.` : `${nombreDe(borrador)} guardada.`));
      avisarCambio();
      if (alGuardar) await alGuardar(mensaje);
    } catch (e) {
      botonGuardar.disabled = false;
      mensaje.replaceChildren(caja("aviso", `No pude guardar: ${e.message} Tus cambios siguen en pantalla.`));
      return;
    }
    if (cambiaCierre) {
      try {
        await reprogramarCierre(borrador, sitio);
        mensaje.replaceChildren(caja("exito", `${nombreDe(borrador)} guardada. La evaluación quedó programada para `
          + `${textoProgramado(new Date(borrador.cierre))}, el nuevo cierre.`));
      } catch (e) {
        mensaje.replaceChildren(caja("aviso", `Se guardó el cierre nuevo, pero no pude reprogramar la evaluación: `
          + `${e.message} Revisa «Últimos trabajos» en Tests.`));
      }
    }
  });

  // ------------------------------------------------ confirmar, volver a borrador, eliminar
  async function confirmarElegida({ enviarAhora = false } = {}) {
    const s = { ...borrador, envio: enviarAhora ? isoAhora() : borrador.envio };
    const problemas = problemasAlConfirmar(s, { enviarAhora });
    if (problemas.length) { mensaje.replaceChildren(caja("aviso", problemas.join(" "))); return; }
    const avisosAntes = avisosDe(s);
    const sale = enviarAhora ? "sale ahora" : `sale ${textoProgramado(new Date(s.envio))}`;
    // El modo no se fija al confirmar: lo lee la evaluación al correr. Se dice
    // el que tiene ahora el interruptor de la instancia.
    const modo = modoDe(s);
    if (!await confirmar(`Vas a confirmar ${nombreDe(s)}: la pregunta ${sale} a los alumnos que no la tienen, y `
      + `${textoAlCierre(modo, textoProgramado(new Date(s.cierre)))} Son correos reales.`
      + `${avisosAntes.length ? `\n\nOjo: ${avisosAntes.join(" ")}` : ""}`
      + `\n\n${enviarAhora ? "" : "Hasta el envío puedes volverla a borrador, y eso anula lo programado. "}¿Confirmas?`,
    enviarAhora ? "Confirmar y enviar ahora" : "Confirmar", "real")) return;
    // «Ahora» es al aceptar el diálogo: el Worker no programa nada que haya pasado hace más de un minuto.
    if (enviarAhora) s.envio = isoAhora();
    let guardo = false;
    try {
      await confirmarInstancia(s, { ...sitio, guardar: async (...a) => { await sitio.guardar(...a); guardo = true; } });
      tras(`${nombreDe(s)} quedó confirmada. La pregunta ${sale} y la evaluación queda programada para `
        + `${textoProgramado(new Date(s.cierre))}. Lo programado se ve en «Últimos trabajos» de Tests.`);
      if (alGuardar) await alGuardar(mensaje);
    } catch (e) {
      // Si alcanzó a guardar, el archivo la tiene en borrador con lo editado; si
      // no, lo editado sigue solo en pantalla, como al fallar «Guardar».
      if (guardo) tras(`No pude confirmar: ${e.message} Sigue en borrador.`, "aviso");
      else mensaje.replaceChildren(caja("aviso", `No pude confirmar: ${e.message} Sigue en borrador y tus cambios siguen en pantalla.`));
    }
  }

  async function volverElegida() {
    if (hayCambios()) { mensaje.replaceChildren(caja("aviso", "Guarda o descarta los cambios antes.")); return; }
    if (!await confirmar(`¿Volver ${nombreDe(borrador)} a borrador? Se anulan el envío y la evaluación programados, `
      + "y no sale nada hasta que la confirmes de nuevo.", "Volver a borrador", "peligro")) return;
    try {
      const r = await volverABorrador(borrador, { ...sitio, enviados: enviadosDe(actual) });
      tras(r.fallaron.length
        ? `Volvió a borrador, pero no pude anular ${r.fallaron.length} trabajo(s) programado(s); igual no mandan `
          + "nada mientras esté en borrador. Anúlalos en «Últimos trabajos» de Tests."
        : `${nombreDe(borrador)} volvió a borrador${r.cancelados ? ` y se anularon ${r.cancelados} trabajo(s) programado(s)` : ""}.`,
      r.fallaron.length ? "aviso" : "exito");
    } catch (e) {
      mensaje.replaceChildren(caja("aviso", `No pude volverla a borrador: ${e.message}`));
    }
  }

  async function eliminarElegida() {
    if (!await confirmar(`¿Eliminar ${nombreDe(borrador)}? Es un borrador que no se ha enviado; se pierden sus preguntas.`,
      "Eliminar", "peligro")) return;
    const nombre = nombreDe(borrador);
    try {
      if (original !== null) await guardarArchivo(quitarInstancia(leerCsv(guardado), actual), `${nombre}: eliminada (borrador)`);
      else releer();
      const sigue = semanasDe(datos)[0]?.numero ?? null;
      borrador = null;
      original = null;
      if (sigue === null) { actual = null; dibujar(); } else elegir(sigue);
      mensaje.replaceChildren(caja("exito", `${nombre} se eliminó.`));
      avisarCambio();
    } catch (e) {
      mensaje.replaceChildren(caja("aviso", `No pude eliminarla: ${e.message}`));
    }
  }

  /** Tipo, envío y cierre de una instancia del formato nuevo, con lo que se puede cambiar según su estado. */
  function camposInstancia() {
    const enviados = enviadosDe(borrador.numero);
    const enBorrador = borrador.estado === "borrador";
    const sugerencias = el("datalist", { id: "tipos-instancia" },
      [...new Set([...TIPOS, ...semanasDe(datos).map((s) => s.tipo)])].map((t) => el("option", { value: t })));
    const tipo = el("input", { type: "text", value: borrador.tipo, list: "tipos-instancia", disabled: !enBorrador,
      placeholder: "Control, Test, Evaluación…" });
    tipo.addEventListener("change", () => {
      const t = tipo.value.trim() || "Instancia";
      borrador = conTipo(datos, borrador, t);
      cambio();
      dibujar();
    });
    const fechaHora = (valor, alCambiar, habilitado) => {
      const campo = el("input", { type: "datetime-local", value: localSantiago(valor), disabled: !habilitado });
      campo.addEventListener("change", () => { alCambiar(isoSantiago(campo.value)); cambio(); });
      return campo;
    };
    const envio = fechaHora(borrador.envio, (v) => { borrador.envio = v; }, enBorrador);
    // Lo que va a leer el alumno, al día con el campo.
    const notaCierre = el("span", { class: "nota-campo" });
    const pintarNotaCierre = () => {
      notaCierre.textContent = lleno(borrador.cierre)
        ? `El alumno lee: «La fecha de entrega es: ${textoFecha(borrador.cierre)}».`
        : "Es la fecha de entrega que lee el alumno, y la hora en que se evalúa.";
    };
    pintarNotaCierre();
    const cierre = fechaHora(borrador.cierre, (v) => { borrador.cierre = v; pintarNotaCierre(); }, true);
    return [
      el("label", { class: "campo" }, "Tipo", tipo, sugerencias,
        el("span", { class: "nota-campo" }, enBorrador ? `Se llamará ${nombreDe(borrador)}.` : "Fijo desde que se confirmó.")),
      el("label", { class: "campo" }, "Envío (hora de Santiago)", envio,
        enBorrador ? null : el("span", { class: "nota-campo" },
          enviados ? "Ya salió." : "Para cambiarlo, vuelve a borrador.")),
      el("label", { class: "campo" }, "Cierre (hora de Santiago)", cierre, notaCierre),
    ];
  }

  /**
   * El interruptor del modo de revisión. Se puede cambiar siempre, también
   * confirmada o enviada, y se guarda con el resto («Guardar …»). Pasar a
   * automático pregunta antes, y dice cuántas correcciones quedan esperando.
   */
  function revisionInstancia() {
    return interruptorRevision({ modo: modoDe(borrador), alCambiar: async (modo) => {
      const pregunta = textoCambioRevision(nombreDe(borrador), modo, envios.esperando.get(borrador.numero) || 0);
      if (pregunta && !await confirmar(pregunta, "Dejar de revisar", "real")) return false;
      borrador.revision = modo;
      cambio();
      return true;
    } });
  }

  function accionesInstancia() {
    const enviados = enviadosDe(borrador.numero);
    if (borrador.estado === "borrador") {
      return el("div", { class: "acciones acciones-instancia" },
        el("button", { class: "primario real", type: "button", onclick: () => confirmarElegida() }, "Confirmar"),
        el("button", { class: "secundario", type: "button", onclick: () => confirmarElegida({ enviarAhora: true }) },
          "Confirmar y enviar ahora"),
        enviados ? null : el("button", { class: "enlace peligro", type: "button", onclick: eliminarElegida }, "Eliminar"),
        el("p", { class: "nota-pie" }, "En borrador se puede editar y simular el envío, pero no sale nada. Al confirmar "
          + "se programan el envío y la evaluación."));
    }
    if (!enviados) {
      return el("div", { class: "acciones acciones-instancia" },
        el("button", { class: "secundario", type: "button", onclick: volverElegida }, "Volver a borrador"),
        el("p", { class: "nota-pie" }, `Confirmada: la pregunta sale ${textoProgramado(new Date(borrador.envio))} y se `
          + `evalúa ${textoProgramado(new Date(borrador.cierre))}. Si cambias el cierre, la evaluación se programa de nuevo.`));
    }
    return el("p", { class: "nota-pie congelado" }, `Ya se envió a ${enviados} alumnos. El nombre y el tema quedan fijos, `
      + "porque el asunto del feedback y el reconocimiento de las respuestas dependen de ellos. Los demás cambios no "
      + "les llegan a quienes ya la recibieron, pero la pauta sí cuenta al corregir. Si cambias el cierre, la "
      + "evaluación se programa de nuevo.");
  }

  function panelSemana() {
    if (!borrador) {
      return el("div", { class: "panel-semana" }, caja("info", legado ? "No hay semanas todavía. Agrega la primera."
        : "Todavía no hay instancias. Crea la primera con «+ Nueva instancia»."));
    }
    const congelado = !legado && enviadosDe(borrador.numero) > 0;
    const tema = el("input", { type: "text", value: borrador.tema, placeholder: "Ej. Extensions of Discrete Choice",
      disabled: congelado });
    tema.addEventListener("input", () => { borrador.tema = tema.value; cambio(); });
    const fecha = el("input", { type: "text", value: borrador.fecha, placeholder: "Ej. lunes 19/10/2026, 10:15" });
    fecha.addEventListener("input", () => { borrador.fecha = fecha.value; cambio(); });
    campoFecha = legado ? fecha : null;
    avisosPorTarjeta = [];
    const agregarPregunta = borrador.preguntas.length < MAX_PREGUNTAS
      ? el("button", { class: "descarga", type: "button", onclick: () => {
        borrador.preguntas.push(preguntaVacia());
        cambio();
        dibujar();
      } }, "+ Agregar pregunta")
      : el("p", { class: "nota-pie" }, `Hasta ${MAX_PREGUNTAS} preguntas por ${legado ? "semana" : "instancia"}.`);

    const nombre = legado ? `Semana ${borrador.numero}` : nombreDe(borrador);
    botonGuardar.textContent = legado ? `Guardar semana ${borrador.numero}` : `Guardar ${nombre}`;
    const estado = legado ? null : estadoInstancia(borrador, enviadosDe(borrador.numero));
    const panel = el("div", { class: "panel-semana" },
      el("h3", {}, nombre, estado ? el("span", { class: `marca estado-instancia ${estado.clase}` }, estado.texto) : null),
      legado
        ? el("div", { class: "campos-semana" },
          el("label", { class: "campo" }, "Tema", tema),
          el("label", { class: "campo" }, "Fecha de entrega", fecha, avisoFecha))
        : el("div", { class: "campos-semana campos-instancia" }, el("label", { class: "campo" }, "Tema", tema),
          ...camposInstancia().filter(Boolean)),
      legado ? null : revisionInstancia(),
      legado ? el("p", { class: "nota-pie" }, "Si la semana ya se envió, los cambios no se reenvían. La pauta sí cuenta al corregir.")
        : accionesInstancia(),
      el("h4", { class: "titulo-preguntas" }, `Preguntas (${borrador.preguntas.length})`),
      borrador.preguntas.map(tarjetaPregunta),
      el("div", { class: "acciones" }, agregarPregunta),
      vistaPrevia(),
      avisos,
      el("div", { class: "barra-guardar" }, estadoGuardado, el("span", { class: "espacio" }), botonDescartar, botonGuardar),
      mensaje);
    cambio();
    return panel;
  }

  function dibujar() {
    pintarLista();
    raiz.replaceChildren(columna, panelSemana());
  }

  (async () => {
    let notas = "";
    try {
      [guardado, etag, notas, respaldo] = await Promise.all([
        leerTexto(semestre, RUTA).catch((e) => { if (e.message === "no existe") return null; throw e; }),
        etagDe(semestre),
        // Para saber qué instancias ya se enviaron y no repetir un id con notas.
        leerTexto(semestre, "notas.csv").catch(() => ""),
        // El modo de respaldo, para las instancias que no dicen el suyo.
        cargarConfiguracion(semestre).then((c) => c.modo, () => null)]);
    } catch (e) {
      raiz.replaceChildren(caja("aviso", `No pude leer preguntas.csv: ${e.message}`));
      return;
    }
    envios = enviosDeNotas(notas);
    // Un semestre sin preguntas.csv (o con solo la cabecera) empieza en el formato nuevo.
    releer();
    if (guardado === null) etag = null;
    const faltan = columnasFaltantes(datos);
    if (faltan.length) {
      raiz.replaceChildren(caja("aviso", `preguntas.csv no tiene las columnas que usa este editor (${faltan.join(", ")}). `
        + "Edítalo desde «Tabla completa»."));
      return;
    }
    legado = esLegado(datos);
    alLeer?.({ legado });
    if (!legado) buscador.setAttribute("aria-label", "Buscar por enunciado, tema o nombre");
    const semanas = semanasDe(datos);
    const numero = semanas.some((s) => s.numero === inicial) ? inicial : semanas[0]?.numero;
    if (numero === undefined) { dibujar(); return; }
    elegir(numero);
  })();

  return raiz;
}

/**
 * Para Tests Semanales: las preguntas de la semana que se va a enviar, de
 * solo lectura, con un enlace al editor. `mostrar(n)` cambia de semana.
 */
export function resumenSemana(semestre, { usaGrupos = true } = {}) {
  const nodo = el("div", { class: "resumen-semana" });
  let datos = null;
  let pedido = null;
  let ultima = null;

  function pintar(numero, { enviada = false } = {}) {
    const s = leerSemana(datos, numero);
    if (!s) {
      nodo.replaceChildren(caja("aviso", esLegado(datos) ? `La semana ${numero} no está en preguntas.csv.`
        : "Esa instancia no está en preguntas.csv."));
      return;
    }
    const editar = el("a", { class: "enlace-editar", href: `/datos#datos/preguntas/${numero}` }, "Editar preguntas");
    const avisos = avisosDe(s);
    // Una fecha vencida en una semana por enviar suele venir copiada de otro semestre.
    const entrega = s.tipo && lleno(s.cierre) ? new Date(s.cierre) : fechaEntrega(s.fecha);
    const textoEntrega = s.tipo && lleno(s.cierre) ? textoFecha(s.cierre) : s.fecha.trim();
    if (!enviada && entrega && entrega < new Date()) avisos.push(`La fecha de entrega (${textoEntrega}) ya pasó.`);
    if (s.tipo && s.estado === "borrador") avisos.push("Está en borrador: se puede simular, pero no sale hasta confirmarla.");
    const lista = (grupo) => el("ol", {}, s.preguntas.map((p) => el("li", {}, (p.igual ? p.control : p[grupo]).texto)));
    const distintas = usaGrupos && s.preguntas.some((p) => !p.igual);
    nodo.replaceChildren(el("div", { class: "tarjeta" },
      el("div", { class: "cabeza-resumen" },
        el("strong", {}, `${nombreDe(s)}${lleno(s.tema) ? ` · ${s.tema}` : ""}`), editar),
      el("p", { class: "nota-pie" }, lleno(textoEntrega) ? `Entrega: ${textoEntrega}` : "Sin fecha de entrega"),
      distintas
        ? el("div", { class: "dos-variantes" }, GRUPOS.map((g) => el("div", {},
          el("span", { class: `pildora ${g}` }, titulo(g)), lista(g))))
        : lista("control"),
      avisos.map((a) => caja("aviso", a))));
  }

  async function mostrar(numero, opciones = {}) {
    ultima = numero;
    if (!datos) {
      pedido ??= leerTexto(semestre, RUTA).then((t) => { datos = leerCsv(t); });
      try {
        await pedido;
      } catch (e) {
        nodo.replaceChildren(caja("aviso", `No pude leer preguntas.csv: ${e.message}`));
        return;
      }
    }
    if (numero === ultima) pintar(numero, opciones);
  }

  return { nodo, mostrar };
}
