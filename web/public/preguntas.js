// Las preguntas de los tests, una semana a la vez.
//
// preguntas.csv tiene una fila por semana y, por cada grupo, hasta tres
// preguntas con su pauta. Editarlo entero en una grilla obliga a buscar la fila
// y a leer párrafos en celdas angostas. Acá se elige la semana, se ven sus
// preguntas como las va a recibir el alumno, y al guardar se reescribe solo esa
// fila: el resto del archivo queda igual, byte a byte (csv.js respeta su formato).

import { api, caja, centrarSeleccion, conDetalle, confirmar, el, normalizar } from "./comun.js";
import { escribirCsv, leerCsv } from "./csv.js";

export const RUTA = "tests_semanales/data/preguntas.csv";
const PLANTILLA_CORREO = "tests_semanales/prompts/correo_pregunta.md";
const GRUPOS = ["control", "tratamiento"];
const MAX_PREGUNTAS = 3;

const titulo = (g) => g[0].toUpperCase() + g.slice(1);
const columna = (grupo, i, pauta) => `${titulo(grupo)} ${pauta ? "Pauta " : ""}P${i}`;
const COLUMNAS = ["Semana", "Tema", "Fecha de Entrega",
  ...GRUPOS.flatMap((g) => [1, 2, 3].flatMap((i) => [columna(g, i, false), columna(g, i, true)]))];
const lleno = (s) => String(s ?? "").trim() !== "";

// ---------------------------------------------------------------- el archivo, sin pantalla

/** Las columnas que el editor necesita y el archivo no tiene. */
export function columnasFaltantes(datos) {
  return COLUMNAS.filter((c) => !datos.columnas.includes(c));
}

function numeroDe(datos, fila) {
  const n = Number.parseInt(String(fila[datos.columnas.indexOf("Semana")] ?? "").trim(), 10);
  return Number.isNaN(n) ? null : n;
}

/** Las semanas del archivo, en orden: [{ numero, tema, fecha, avisos }]. */
export function semanasDe(datos) {
  return datos.filas.map((f) => numeroDe(datos, f)).filter((n) => n !== null)
    .sort((a, b) => a - b)
    .map((n) => {
      const s = leerSemana(datos, n);
      return { numero: n, tema: s.tema, fecha: s.fecha, avisos: avisosDe(s, true) };
    });
}

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
  return { numero, tema: v("Tema"), fecha: v("Fecha de Entrega"), preguntas };
}

/**
 * Qué cambió en una semana, en una frase para el registro: "Semana 11: cambió
 * la fecha de entrega y la pregunta 2 (control)". `antes` es null si es nueva.
 */
export function cambiosSemana(numero, antes, despues) {
  if (!antes) return `Semana ${numero}: semana nueva`;
  const cambios = [];
  if (antes.tema !== despues.tema) cambios.push("el tema");
  if (antes.fecha !== despues.fecha) cambios.push(`la fecha de entrega (${despues.fecha.trim() || "vacía"})`);
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
  if (!cambios.length) return `Semana ${numero}: sin cambios`;
  const lista = cambios.length > 1 ? `${cambios.slice(0, -1).join(", ")} y ${cambios[cambios.length - 1]}` : cambios[0];
  return `Semana ${numero}: cambió ${lista}`.replace(/cambió (agregó|quitó)/, "$1");
}

/**
 * El archivo con la fila de esa semana reemplazada; las demás filas no se tocan.
 * Las preguntas se escriben en orden (P1, P2...) y una pregunta "igual" se
 * copia a los dos grupos, que es lo que lee preguntas.py.
 */
export function escribirSemana(datos, numero, semana) {
  const i = datos.filas.findIndex((f) => numeroDe(datos, f) === numero);
  if (i < 0) throw new Error(`No existe la semana ${numero} en el archivo.`);
  const fila = [...datos.filas[i]];
  const poner = (c, valor) => { fila[datos.columnas.indexOf(c)] = valor; };
  poner("Tema", semana.tema);
  poner("Fecha de Entrega", semana.fecha);
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
  const n = q.match(/^(?:semana|sem\.?)?\s*(\d+)$/);
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
    avisos.push(corto ? "sin preguntas" : "La semana no tiene preguntas: no se puede enviar.");
    return avisos;
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

/** Igual que _construir_bloque_preguntas() de modulos/tests/enviar.py. */
export function bloquePreguntas(preguntas) {
  if (preguntas.length === 1) {
    return `<p>La pregunta de la semana es:</p>\n<blockquote style="${ESTILO_CITA}">\n  ${preguntas[0]}\n</blockquote>`;
  }
  return ["<p>Las preguntas de la semana son:</p>",
    ...preguntas.map((p, i) => `<blockquote style="${ESTILO_CITA}">\n  ${i + 1}. ${p}\n</blockquote>`)].join("\n");
}

/** El correo que recibe un alumno de ese grupo: { asunto, html }. */
export function correoDe(plantilla, semana, grupo, nombre = "Ana") {
  const preguntas = semana.preguntas.map((p) => (p.igual ? p.control : p[grupo]).texto.trim()).filter(lleno);
  return {
    asunto: `Evaluación de Progreso Individual Módulo ${semana.numero}: ${semana.tema.trim()}`,
    html: plantilla
      .replaceAll("{NOMBRE}", nombre)
      .replaceAll("{TEMA}", semana.tema.trim())
      .replaceAll("{FECHA_ENTREGA}", semana.fecha.trim())
      .replaceAll("{BLOQUE_PREGUNTAS}", bloquePreguntas(preguntas))
      .replaceAll("{SEMANA}", String(semana.numero)),
  };
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
 * El editor: la lista de semanas a la izquierda y la semana elegida a la
 * derecha. `alCambiarSemana(n)` avisa qué semana se está viendo (para la URL),
 * `alCambiar(hayCambios)` si hay algo sin guardar, y `alGuardar(destino)` corre
 * después de guardar.
 */
export function editorPreguntas({ semestre, semana: inicial, usaGrupos = true,
  alCambiarSemana, alCambiar, alGuardar } = {}) {
  const raiz = el("div", { class: "editor-preguntas" }, el("p", { class: "cargando" }, "Cargando las preguntas…"));
  let datos = null; // el archivo como se ve ahora
  let guardado = null; // el texto del archivo tal como está en la nube
  let etag = null;
  let actual = null; // número de la semana elegida
  let borrador = null; // esa semana, con lo que se ha editado
  let original = null; // la misma semana al abrirla, para saber si hay cambios
  let plantilla = null; // correo_pregunta.md, para la vista previa

  const hayCambios = () => borrador !== null && JSON.stringify(borrador) !== original;
  const avisarCambio = () => alCambiar?.(hayCambios());

  async function descartarSiHace() {
    if (!hayCambios()) return true;
    if (!await confirmar(`La semana ${actual} tiene cambios sin guardar. ¿Descartarlos?`, "Descartar", "peligro")) {
      return false;
    }
    datos = leerCsv(guardado);
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

  // ------------------------------------------------ buscar
  // Filtra la lista de semanas. Lo escrito se mantiene al elegir una semana.
  const buscador = el("input", { type: "search", placeholder: "Buscar…",
    "aria-label": "Buscar por enunciado, tema o número de semana" });
  const grupoBuscado = usaGrupos ? el("select", { "aria-label": "Buscar en el grupo" },
    el("option", { value: "" }, "Ambos"), GRUPOS.map((g) => el("option", { value: g }, titulo(g)))) : null;
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

  // ------------------------------------------------ la lista de semanas
  function listaSemanas() {
    const consulta = buscador.value.trim();
    const hallados = consulta ? new Map(buscarPreguntas(datos, consulta, usaGrupos ? grupoBuscado.value : "control")
      .map((r) => [r.numero, r.coincidencias])) : null;
    const semanas = semanasDe(datos).filter((s) => !hallados || hallados.has(s.numero));
    const agregar = el("button", { class: "agregar-semana", type: "button", onclick: async () => {
      if (!await descartarSiHace()) return;
      const [nuevos, numero] = agregarSemana(datos);
      datos = nuevos;
      actual = numero;
      borrador = { ...leerSemana(datos, numero),
        preguntas: [{ control: { texto: "", pauta: "" }, tratamiento: { texto: "", pauta: "" }, igual: true }] };
      original = null; // una semana nueva no existe hasta guardarla
      alCambiarSemana?.(numero);
      avisarCambio();
      dibujar();
    } }, "+ Agregar semana");
    // En celular es una tira que se desliza: que se vea la semana elegida, no la 1.
    const lista = el("nav", { class: "lista-semanas", "aria-label": "Semanas" },
      hallados && !semanas.length ? el("p", { class: "nota-pie sin-resultados" }, "Sin resultados.") : null,
      semanas.map((s) => el("button", {
        type: "button", class: "item-semana", "aria-current": s.numero === actual ? "true" : null,
        onclick: async () => { if (s.numero !== actual && await descartarSiHace()) elegir(s.numero); },
      },
      el("span", { class: "num-semana" }, `Semana ${s.numero}`),
      el("span", { class: "tema-semana" }, lleno(s.tema) ? s.tema : "Sin tema"),
      lineaHallada(hallados?.get(s.numero)?.[0], consulta),
      s.avisos.length ? el("span", { class: "marcas" }, s.avisos.map((a) => el("span", { class: "marca" }, a))) : null)),
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
        usaGrupos ? el("label", { class: "interruptor" }, distinta, "Distinta para Control y Tratamiento") : null,
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
      const { asunto, html } = correoDe(plantilla, borrador, grupo);
      const distintas = usaGrupos && borrador.preguntas.some((p) => !p.igual);
      contenido.replaceChildren(
        distintas ? el("div", { class: "chips" }, GRUPOS.map((g) => el("button", {
          type: "button", class: "chip", "aria-pressed": String(g === grupo), onclick: () => mostrar(g),
        }, `Como ${titulo(g)}`))) : "",
        el("p", { class: "asunto" }, el("span", { class: "tenue" }, "Asunto: "), asunto),
        // Sin permisos: el HTML del correo se muestra, pero no puede correr nada en el sitio.
        el("iframe", { class: "correo", sandbox: "", srcdoc: html, title: `Correo de la semana ${borrador.numero}` }));
    };
    detalles.addEventListener("toggle", async () => {
      if (!detalles.open) return;
      if (plantilla === null) {
        contenido.replaceChildren(el("p", { class: "cargando" }, "Cargando la plantilla del correo…"));
        try {
          plantilla = await leerTexto(semestre, PLANTILLA_CORREO);
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
    const sinFecha = borrador.preguntas.length > 0 && !lleno(borrador.fecha);
    avisoFecha.textContent = sinFecha ? "Falta la fecha: el correo diría «La fecha de entrega es:» y nada más." : "";
    campoFecha?.classList.toggle("falta", sinFecha);
    for (const { nodo, p, i } of avisosPorTarjeta) {
      nodo.replaceChildren(...avisosDePregunta(p, i).map((a) => el("p", { class: "aviso-campo" }, a)));
    }
    avisos.replaceChildren(borrador.preguntas.length ? ""
      : caja("aviso", "La semana no tiene preguntas: no se puede enviar."));
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
    if (!await confirmar(`¿Descartar los cambios de la semana ${actual}?`, "Descartar", "peligro")) return;
    datos = leerCsv(guardado);
    const sigue = leerSemana(datos, actual) ? actual : semanasDe(datos)[0]?.numero ?? null;
    if (sigue === null) { borrador = null; dibujar(); return; }
    elegir(sigue);
  });

  botonGuardar.addEventListener("click", async () => {
    botonGuardar.disabled = true;
    try {
      const nuevos = escribirSemana(datos, actual, borrador);
      const texto = escribirCsv(nuevos);
      await api(urlArchivo(semestre, RUTA), {
        method: "PUT", body: texto,
        headers: { "content-type": "text/csv; charset=utf-8", ...(etag ? { "if-match": etag } : { "if-none-match": "*" }),
          ...conDetalle(cambiosSemana(actual, original ? JSON.parse(original) : null, borrador)) },
      });
      datos = leerCsv(texto);
      guardado = texto;
      etag = await etagDe(semestre);
      borrador = leerSemana(datos, actual);
      original = JSON.stringify(borrador);
      dibujar();
      mensaje.replaceChildren(caja("exito", `Semana ${actual} guardada.`));
      avisarCambio();
      if (alGuardar) await alGuardar(mensaje);
    } catch (e) {
      botonGuardar.disabled = false;
      mensaje.replaceChildren(caja("aviso", `No pude guardar: ${e.message} Tus cambios siguen en pantalla.`));
    }
  });

  function panelSemana() {
    if (!borrador) {
      return el("div", { class: "panel-semana" }, caja("info", "No hay semanas todavía. Agrega la primera."));
    }
    const tema = el("input", { type: "text", value: borrador.tema, placeholder: "Ej. Extensions of Discrete Choice" });
    tema.addEventListener("input", () => { borrador.tema = tema.value; cambio(); });
    const fecha = el("input", { type: "text", value: borrador.fecha, placeholder: "Ej. lunes 19/10/2026, 10:15" });
    fecha.addEventListener("input", () => { borrador.fecha = fecha.value; cambio(); });
    campoFecha = fecha;
    avisosPorTarjeta = [];
    const agregarPregunta = borrador.preguntas.length < MAX_PREGUNTAS
      ? el("button", { class: "descarga", type: "button", onclick: () => {
        borrador.preguntas.push({ control: { texto: "", pauta: "" }, tratamiento: { texto: "", pauta: "" }, igual: true });
        cambio();
        dibujar();
      } }, "+ Agregar pregunta")
      : el("p", { class: "nota-pie" }, `Hasta ${MAX_PREGUNTAS} preguntas por semana.`);

    botonGuardar.textContent = `Guardar semana ${borrador.numero}`;
    const panel = el("div", { class: "panel-semana" },
      el("h3", {}, `Semana ${borrador.numero}`),
      el("div", { class: "campos-semana" },
        el("label", { class: "campo" }, "Tema", tema),
        el("label", { class: "campo" }, "Fecha de entrega", fecha, avisoFecha)),
      el("p", { class: "nota-pie" }, "Si la semana ya se envió, los cambios no se reenvían. La pauta sí cuenta al corregir."),
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
    try {
      [guardado, etag] = await Promise.all([leerTexto(semestre, RUTA), etagDe(semestre)]);
    } catch (e) {
      raiz.replaceChildren(caja("aviso", e.message === "no existe"
        ? "Este semestre todavía no tiene preguntas.csv. Súbelo desde «Tabla completa»."
        : `No pude leer preguntas.csv: ${e.message}`));
      return;
    }
    datos = leerCsv(guardado);
    const faltan = columnasFaltantes(datos);
    if (faltan.length) {
      raiz.replaceChildren(caja("aviso", `preguntas.csv no tiene las columnas que usa este editor (${faltan.join(", ")}). `
        + "Edítalo desde «Tabla completa»."));
      return;
    }
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
      nodo.replaceChildren(caja("aviso", `La semana ${numero} no está en preguntas.csv.`));
      return;
    }
    const editar = el("a", { class: "enlace-editar", href: `/datos#datos/preguntas/${numero}` }, "Editar preguntas");
    const avisos = avisosDe(s);
    // Una fecha vencida en una semana por enviar suele venir copiada de otro semestre.
    const entrega = fechaEntrega(s.fecha);
    if (!enviada && entrega && entrega < new Date()) avisos.push(`La fecha de entrega (${s.fecha.trim()}) ya pasó.`);
    const lista = (grupo) => el("ol", {}, s.preguntas.map((p) => el("li", {}, (p.igual ? p.control : p[grupo]).texto)));
    const distintas = usaGrupos && s.preguntas.some((p) => !p.igual);
    nodo.replaceChildren(el("div", { class: "tarjeta" },
      el("div", { class: "cabeza-resumen" },
        el("strong", {}, `Semana ${numero}${lleno(s.tema) ? ` · ${s.tema}` : ""}`), editar),
      el("p", { class: "nota-pie" }, lleno(s.fecha) ? `Entrega: ${s.fecha}` : "Sin fecha de entrega"),
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
