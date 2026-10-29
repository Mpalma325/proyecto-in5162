// Reportería del curso: la misma pantalla de inicio de Streamlit, en web.
//
// Los cálculos no están acá. La página carga modulos/datos/agregaciones.py y lo
// corre con Pyodide, así que cada número sale de la misma función de Python que
// usa Streamlit. Este archivo solo trae datos, pide cálculos y dibuja.
// La excepción es la franja de la semana en curso, que es solo contar filas de
// la última semana enviada y no existe en Streamlit (ver semanaActual()).

import { api, caja, el, esOscuro, navegacion, pedirTrabajo, seguirTrabajo, vistaCorreo } from "./comun.js";
import { descargar, exportarCsv, leerCsv } from "./csv.js";
import { leerSemana } from "./preguntas.js";
import { seccionSabana } from "./sabana.js";

document.getElementById("nav")?.replaceWith(navegacion());

const ALTO = 260;
// Misma rampa que app/main.py: la originalidad es una escala ordenada, así que
// va en un solo tono de claro a oscuro, pegado al nivel y no al orden de aparición.
const RAMPA_CLARA = ["#d6e4f5", "#a9c7ea", "#6ea8db", "#3d82c4", "#1a5490"];
// En modo oscuro la rampa va al revés en luminosidad: el nivel alto sigue siendo
// el que más contrasta con el fondo, y el más bajo no se funde con él.
const RAMPA_OSCURA = ["#4a72a3", "#5f8bc0", "#7aa9dd", "#a3c6ec", "#cfe2f7"];
const SIN_NIVEL = "#9e9e9e";
const MEDIA_OSCURO = matchMedia("(prefers-color-scheme: dark)");
const MEDIA_ANGOSTA = matchMedia("(max-width: 720px)");
const rampa = () => (esOscuro() ? RAMPA_OSCURA : RAMPA_CLARA);

const PESTANAS = [
  { id: "Alumnos" }, { id: "Curso" }, { id: "Originalidad" }, { id: "Grupos" }, { id: "Correlaciones" },
  { id: "Pendientes" },
  { id: "Descargar", etiqueta: "Descargar datos" },
];

const app = document.getElementById("app");
const estado = {
  semestres: [], semestre: null, activo: null,
  items: [], grupos: [], selItems: new Set(), selGrupos: new Set(),
  pestana: "Alumnos", alumno: null,
  // preguntas.csv del semestre, para mostrar en la ficha lo que se le preguntó a cada uno.
  preguntas: null,
  // correo_correccion.md, que envuelve la corrección del agente en el correo.
  plantillaCorreccion: null,
  // Filas del semestre tal como llegan (solo las del roster, como en Python).
  filas: [],
  // La última semana enviada (semanaActual), sobre todo el semestre.
  semana: null,
  filtrosAbiertos: null, ordenAlumnos: null, busquedaAlumnos: "", irAFicha: false,
  // Correlaciones: si se mira por alumno o por respuesta, y el par elegido en cada caso.
  correlacion: { unidad: "alumno", alumno: ["NotaMedia", "TasaRespuesta"], respuesta: ["Nota", "Palabras"] },
};
let py = null;

// ---------------------------------------------------------------- utilidades

const hay = (v) => v !== null && v !== undefined;
/** 5.55 -> "5,55"; con un decimal fijo por defecto, como se escriben las notas. */
const numero = (v, decimales = 1) => (hay(v)
  ? Number(v).toLocaleString("es-CL", { minimumFractionDigits: decimales, maximumFractionDigits: decimales })
  : "—");
const entero = (v) => (hay(v) ? Number(v).toLocaleString("es-CL") : "—");
const plural = (n, uno, varios) => `${entero(n)} ${n === 1 ? uno : varios}`;
const posicion = (item) => estado.items.indexOf(item);
const normalizar = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/**
 * Un indicador. Lo que explica el número va en `sub`, visible siempre: en un
 * celular no hay mouse para leer un title. `accion` es el texto del enlace.
 */
function kpi({ etiqueta, valor, sub = null, accion = null, alClic = null }) {
  const lineas = [sub].flat().filter(Boolean);
  return el("div", {
    class: alClic ? "kpi clic" : "kpi", onclick: alClic,
    role: alClic ? "button" : null, tabindex: alClic ? "0" : null,
    onkeydown: alClic ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); alClic(); } } : null,
  },
    el("div", { class: "etiqueta" }, etiqueta),
    el("div", { class: "valor" }, hay(valor) ? valor : "—"),
    lineas.map((l) => el("div", { class: "sub" }, l)),
    accion ? el("div", { class: "accion" }, accion) : null);
}

/**
 * Un gráfico en su tarjeta: el título y lo que pasa al hacer clic van arriba,
 * a la vista; la explicación de cómo leerlo, abajo.
 */
function tarjeta(titulo, nodo, { pista = null, pie = null } = {}) {
  if (!nodo) return null;
  const esGrafico = nodo instanceof Node && nodo.classList.contains("grafico");
  return el("div", { class: "tarjeta" },
    titulo ? el("h3", { class: "titulo-grafico" }, titulo,
      pista && esGrafico ? el("span", { class: "clic" }, pista) : null) : null,
    nodo,
    pie && esGrafico ? el("p", { class: "pie-grafico" }, pie) : null);
}


function tabla(filas, columnas = null) {
  if (!filas.length) return el("p", { class: "tenue" }, "Sin filas.");
  const cols = columnas || Object.keys(filas[0]);
  return el("div", { class: "tabla-envoltura" },
    el("table", {},
      el("thead", {}, el("tr", {}, cols.map((c) => el("th", {}, c)))),
      el("tbody", {}, filas.map((f) =>
        el("tr", {}, cols.map((c) => el("td", {}, formatear(f[c]))))))));
}

function formatear(v) {
  if (v === null || v === undefined) return "";
  if (typeof v === "boolean") return v ? "sí" : "no";
  if (Array.isArray(v)) return v.join(", ");
  return v;
}

function desplegable(titulo, ...contenido) {
  return el("details", {}, el("summary", {}, titulo), el("div", { class: "contenido" }, contenido));
}

function haceCuanto(iso) {
  if (!iso) return null;
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (Number.isNaN(min)) return null;
  if (min < 1) return "recién";
  if (min < 60) return `hace ${min} min`;
  const h = Math.round(min / 60);
  if (h < 48) return `hace ${h} h`;
  return `hace ${Math.round(h / 24)} días`;
}

const fechaValida = (iso) => {
  const d = new Date(iso);
  return iso && !Number.isNaN(d.getTime()) ? d : null;
};
const fechaLarga = (d) => d.toLocaleDateString("es-CL", { day: "numeric", month: "long" });
const fechaHora = (d) => d.toLocaleString("es-CL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

/**
 * La corrección como le llegó al alumno: dentro de correo_correccion.md si el
 * semestre lo tiene, con el asunto del hilo. El cuerpo enviado no se guarda,
 * así que se rearma con la plantilla de hoy; las reconstruidas desde el buzón
 * son texto plano y se muestran así.
 */
function correoEvaluacion(c) {
  // Lo mismo que _normalizar_html_gpt y _construir_cuerpo_correccion (evaluar.py).
  let evaluacion = String(c.EvaluacionIA).trim();
  if (evaluacion.startsWith("```")) evaluacion = evaluacion.replace(/^```(?:html)?\s*/, "").replace(/\s*```$/, "").trim();
  const html = /<(p|br|b|strong|hr|div)\b/i.test(evaluacion);
  const plantilla = html ? estado.plantillaCorreccion : null;
  // Sin nombre en el roster, el panel pone el correo en Nombre; Python escribía "estudiante".
  const nombre = (c.Nombre && c.Nombre !== c.Correo && c.Nombre.trim().split(/\s+/)[0]) || "estudiante";
  const semana = estado.preguntas ? leerSemana(estado.preguntas, Number(c.Item)) : null;
  return vistaCorreo({
    asunto: semana ? `Re: Evaluación de Progreso Individual Módulo ${c.Item}: ${semana.tema}` : "",
    para: c.Correo, nombre: c.Nombre, html,
    // Con función: como texto de reemplazo, un "$&" o "$'" de la evaluación se interpretaría.
    cuerpo: plantilla ? plantilla.replaceAll("{NOMBRE}", () => nombre).replaceAll("{EVALUACION}", () => evaluacion) : evaluacion,
  }, {
    aviso: plantilla ? "Rearmado con la plantilla actual del correo: el saludo o el pie pueden diferir de lo enviado."
      : html ? null : "Texto recuperado del buzón: se ve sin el formato original.",
  });
}

// ---------------------------------------------------------------- gráficos

/** Los colores del tema que está viendo la persona, leídos de estilos.css. */
function colores() {
  const css = getComputedStyle(document.documentElement);
  const v = (n) => css.getPropertyValue(n).trim();
  const oscuro = esOscuro();
  return {
    texto: v("--texto"), tenue: v("--tenue"), linea: v("--linea"), caja: v("--caja"),
    acento: v("--acento"), ok: v("--ok"), rojo: oscuro ? "#ef7a7a" : "#c62828",
  };
}

function temaVega() {
  const c = colores();
  return {
    background: null,
    title: { color: c.texto, subtitleColor: c.tenue, fontSize: 14, anchor: "start" },
    axis: { labelColor: c.tenue, titleColor: c.tenue, gridColor: c.linea, domainColor: c.linea, tickColor: c.linea },
    // Etiquetas horizontales: giradas, las categorías largas ("Muy Baja") se
    // cortaban o desaparecían por superposición.
    axisX: { labelAngle: 0, labelOverlap: "greedy" },
    legend: { labelColor: c.tenue, titleColor: c.tenue },
    view: { stroke: null },
    // El azul por defecto de Vega no cambia con el tema; el acento del sitio sí.
    // Control y Tratamiento con los mismos colores que en el editor de preguntas.
    mark: { color: c.acento },
    range: { category: [c.acento, c.ok, "#e08a5f", c.tenue] },
  };
}

/**
 * Dibuja un gráfico. Si recibe `alClic`, cada barra o punto es clickeable y
 * llama a esa función con los datos de lo que se tocó.
 */
function grafico(spec, alClic = null) {
  const nodo = el("div", { class: "grafico" });
  const config = temaVega();
  if (alClic) config.mark = { ...config.mark, cursor: "pointer" };
  const completo = {
    $schema: "https://vega.github.io/schema/vega-lite/v6.json",
    width: "container",
    autosize: { type: "fit", contains: "padding" },
    config,
    ...spec,
  };
  // Se dibuja cuando el nodo ya está en la página, para que tome su ancho.
  requestAnimationFrame(async () => {
    const { view } = await vegaEmbed(nodo, completo, { actions: false, renderer: "svg" });
    if (alClic) {
      view.addEventListener("click", (_evento, item) => {
        if (item && item.datum && !Array.isArray(item.datum)) alClic(item.datum);
      });
    }
  });
  return nodo;
}

const campo = (field, type, extra = {}) => ({ field, type, ...extra });
const tooltips = (campos) => campos.map((c) => ({ field: c }));

/** Eje de notas ajustado a los datos con medio punto de margen, dentro de 1 a 7. */
function dominioNotas(valores) {
  const v = valores.filter(hay);
  if (!v.length) return [1, 7];
  return [Math.max(1, Math.floor(Math.min(...v) - 0.5)), Math.min(7, Math.ceil(Math.max(...v) + 0.5))];
}

/**
 * Serie por semana, como `_linea` de main.py. Todas las semanas quedan en el
 * eje aunque no tengan valor (la última puede no tener notas todavía). La
 * semana en curso va con punto hueco y el tramo que llega a ella, punteado.
 */
function linea(filas, y, tituloEje, { dominio = null, alClic = null, enCurso = null } = {}) {
  const datos = filas.filter((f) => hay(f[y]));
  if (!datos.length) return null;
  const c = colores();
  const semanas = filas.map((f) => f.Item);
  const i = enCurso ? datos.findIndex((f) => f.Item === enCurso) : -1;
  const cerradas = i >= 0 ? datos.filter((f) => f.Item !== enCurso) : datos;
  const tramo = i > 0 ? [datos[i - 1], datos[i]] : [];
  return grafico({
    height: ALTO,
    encoding: {
      x: campo("Item", "ordinal", { title: "Semana", scale: { domain: semanas } }),
      y: campo(y, "quantitative", { title: tituloEje, scale: dominio ? { domain: dominio } : { zero: false } }),
      tooltip: tooltips(Object.keys(filas[0])),
    },
    layer: [
      { data: { values: cerradas }, mark: { type: "line" } },
      tramo.length ? { data: { values: tramo }, mark: { type: "line", strokeDash: [4, 4] } } : null,
      {
        data: { values: datos }, mark: { type: "point", filled: true, size: 60, opacity: 1, strokeWidth: 2 },
        encoding: {
          fill: i >= 0
            ? { condition: { test: `datum.Item === ${JSON.stringify(enCurso)}`, value: c.caja }, value: c.acento }
            : { value: c.acento },
          stroke: { value: c.acento },
        },
      },
    ].filter(Boolean),
  }, alClic);
}

function escalaOriginalidad(filasConNivel) {
  const etiquetas = filasConNivel.map((f) => f.Originalidad);
  const rango = filasConNivel.map((f) => (f.Nivel ? rampa()[f.Nivel - 1] : SIN_NIVEL));
  return { etiquetas, escala: { domain: etiquetas, range: rango } };
}

// ---------------------------------------------------------------- Python

// Las filas del semestre se cargan una vez en Python y quedan ahí; cada cálculo
// trabaja sobre la vista filtrada, en vez de mandar todo de vuelta en cada uno.
const PUENTE = `
import json
_TODAS, _VISTA = [], []

def _cargar(j):
    global _TODAS
    _TODAS = [f for f in json.loads(j) if f.get("EnRoster")]
    # JSON no distingue 7 de 7.0, y al pasar por JavaScript las notas enteras
    # llegan como int. En Python la nota es siempre float: sin esto la página
    # mostraría "7" donde Streamlit muestra "7.0".
    for f in _TODAS:
        if f.get("Nota") is not None:
            f["Nota"] = float(f["Nota"])
    return json.dumps({"items": items(_TODAS), "grupos": grupos(_TODAS)})

def _filtrar(items_j, grupos_j):
    global _VISTA
    _VISTA = filtrar(_TODAS, items=json.loads(items_j), grupos=json.loads(grupos_j))
    return len(_VISTA)

def _calc(nombre):
    return json.dumps(globals()[nombre](_VISTA), ensure_ascii=False)

def _ficha(correo):
    return json.dumps(ficha(correo, _VISTA), ensure_ascii=False)

def _ficha_todas(correo):
    # La ficha muestra todo lo del alumno, sin los filtros de arriba: si no, había
    # que volver a marcar semanas para ver lo que ya estaba.
    return json.dumps(ficha(correo, filtrar(_TODAS, grupos=None)), ensure_ascii=False)

def _casillas(criterio_j):
    filas = casillas(_VISTA, **json.loads(criterio_j))
    # El nivel lo calcula Python, que es donde vive la escala, para pintar la
    # etiqueta con el mismo tono que los gráficos.
    return json.dumps([{**f, "Nivel": nivel_originalidad(f.get("Originalidad"))} for f in filas],
                      ensure_ascii=False)

def _vista():
    return json.dumps(_VISTA, ensure_ascii=False)
`;

async function iniciarPython() {
  py = await loadPyodide();
  const codigo = await (await fetch("/py/agregaciones.py", { cache: "no-store" })).text();
  py.runPython(codigo);
  py.runPython(PUENTE);
}

function llamar(nombre, ...args) {
  const f = py.globals.get(nombre);
  try {
    const r = f(...args);
    return typeof r === "string" ? JSON.parse(r) : r;
  } finally {
    f.destroy();
  }
}
const calc = (nombre) => llamar("_calc", nombre);

// ---------------------------------------------------------------- datos


async function cargarSemestre(id) {
  estado.semestre = id;
  estado.alumno = null;
  const filas = await api(`/api/panel/${encodeURIComponent(id)}`);
  const meta = llamar("_cargar", JSON.stringify(filas));
  estado.items = meta.items;
  estado.grupos = meta.grupos;
  estado.selItems = new Set(meta.items);
  estado.selGrupos = new Set(meta.grupos);
  estado.filas = filas.filter((f) => f.EnRoster);
  estado.semana = semanaActual(estado.filas, estado.items);
  estado.preguntas = null;
  estado.plantillaCorreccion = null;
  fetch(`/api/archivo/${encodeURIComponent(id)}/tests_semanales/prompts/correo_correccion.md`, { cache: "no-store" })
    .then((r) => (r.ok ? r.text() : ""))
    .then((texto) => {
      if (!texto || estado.semestre !== id) return;
      estado.plantillaCorreccion = texto;
      if (estado.pestana === "Alumnos") dibujarPestana();
    })
    .catch(() => {});
  fetch(`/api/archivo/${encodeURIComponent(id)}/tests_semanales/data/preguntas.csv`, { cache: "no-store" })
    .then((r) => (r.ok ? r.text() : ""))
    .then((texto) => {
      if (!texto || estado.semestre !== id) return;
      estado.preguntas = leerCsv(texto);
      if (estado.pestana === "Alumnos") dibujarPestana();
    })
    .catch(() => {});
}

/**
 * La última semana enviada, sobre todo el semestre (sin los filtros): cuántos
 * la recibieron, respondieron y tienen nota. Si todavía no tiene ninguna nota
 * se trata como "en curso": a quienes les falta responder no están atrasados,
 * todavía pueden hacerlo. Usa los mismos criterios que agregaciones.py.
 */
function semanaActual(filas, items) {
  for (let i = items.length - 1; i >= 0; i--) {
    const item = items[i];
    const sub = filas.filter((f) => f.Item === item);
    const enviados = sub.filter((f) => f.Enviado);
    if (!enviados.length) continue;
    const respondieron = sub.filter((f) => f.Respondio).length;
    const evaluados = sub.filter((f) => hay(f.Nota)).length;
    const fechas = enviados.map((f) => fechaValida(f.FechaEnvio)).filter(Boolean).sort((a, b) => a - b);
    return {
      item, enviados: enviados.length, respondieron, evaluados, enCurso: evaluados === 0,
      enviada: fechas.length ? fechas[fechas.length - 1] : null,
      sinResponder: sub.filter((f) => f.Enviado && !f.Respondio),
      sinNota: sub.filter((f) => f.Respondio && !hay(f.Nota)),
    };
  }
  return null;
}

/** El ítem de la semana en curso, o null si la última enviada ya tiene notas. */
const itemEnCurso = () => (estado.semana && estado.semana.enCurso ? estado.semana.item : null);

// ---------------------------------------------------------------- detalle

function colorOriginalidad(nivel) {
  const fondo = nivel ? rampa()[nivel - 1] : SIN_NIVEL;
  return `background:${fondo};color:${textoSobre(fondo)}`;
}

/** Blanco o casi negro, el que más contraste tenga sobre ese fondo. */
function textoSobre(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((u) => (u <= 0.03928 ? u / 12.92 : ((u + 0.055) / 1.055) ** 2.4));
  const l = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return 1.05 / (l + 0.05) >= (l + 0.05) / 0.061 ? "#ffffff" : "#1c1b1a";
}

function irAFicha(correo) {
  cerrarDetalle();
  estado.pestana = "Alumnos";
  estado.alumno = correo;
  estado.irAFicha = true;
  history.replaceState(null, "", "#Alumnos");
  dibujar();
}

function tarjetaCasilla(c) {
  const nota = c.NotaTexto || (c.Respondio ? "sin nota" : "sin responder");
  return el("details", { class: "casilla" },
    el("summary", {},
      el("span", { class: "nombre" }, c.Nombre),
      el("span", { class: "nota" }, nota),
      el("span", { class: "orig" },
        c.Originalidad ? el("span", { class: "etiqueta-orig", style: colorOriginalidad(c.Nivel) }, c.Originalidad) : null),
      el("span", { class: "meta" }, `semana ${c.Item} · ${c.Grupo || "sin grupo"}`)),
    el("div", { class: "contenido" },
      c.Respuesta
        ? [el("p", {}, el("strong", {}, "Lo que respondió")), el("div", { class: "respuesta" }, c.Respuesta)]
        : el("p", { class: "tenue" }, c.Respondio ? "No hay texto de respuesta guardado." : "No respondió esta semana."),
      c.EvaluacionIA
        ? el("div", { class: "evaluacion" }, el("p", {}, el("strong", {}, "El correo que recibió")),
          correoEvaluacion(c))
        : null,
      el("button", { class: "ir-ficha", type: "button", onclick: () => irAFicha(c.Correo) },
        "Ver su ficha completa →")));
}

/** "Copiar los 12 correos", separados por coma para pegarlos en el destinatario. */
function botonCopiar(correos) {
  const texto = correos.length === 1 ? "Copiar el correo" : `Copiar los ${correos.length} correos`;
  const boton = el("button", { class: "secundario", type: "button" }, texto);
  boton.addEventListener("click", async () => {
    const lista = correos.join(", ");
    try {
      await navigator.clipboard.writeText(lista);
    } catch {
      // Sin permiso para el portapapeles: se muestran para copiarlos a mano.
      window.prompt("Copia los correos:", lista);
      return;
    }
    boton.textContent = correos.length === 1 ? "Correo copiado" : `${correos.length} correos copiados`;
    setTimeout(() => { boton.textContent = texto; }, 2500);
  });
  return boton;
}

/**
 * Quienes no respondieron, una línea por alumno con sus semanas: la misma
 * persona no se repite una vez por semana. Primero a quienes les faltan más.
 */
function listaPorAlumno(lista, enCurso = itemEnCurso()) {
  const gente = new Map();
  for (const c of lista) {
    if (!gente.has(c.Correo)) gente.set(c.Correo, { Nombre: c.Nombre, Correo: c.Correo, Grupo: c.Grupo, semanas: [] });
    gente.get(c.Correo).semanas.push(c.Item);
  }
  const orden = [...gente.values()]
    .map((g) => ({ ...g, semanas: [...new Set(g.semanas)].sort((a, b) => posicion(a) - posicion(b)) }))
    .sort((a, b) => b.semanas.length - a.semanas.length || a.Nombre.localeCompare(b.Nombre, "es"));
  const semanas = (s) => `${s.length === 1 ? "semana" : "semanas"} `
    + s.map((x) => (x === enCurso ? `${x} (en curso)` : x)).join(", ");
  return el("div", { class: "por-alumno" },
    el("div", { class: "acciones" }, botonCopiar(orden.map((g) => g.Correo)),
      el("span", { class: "tenue" }, plural(orden.length, "alumno", "alumnos"))),
    el("ul", { class: "lista-alumnos" }, orden.map((g) => el("li", {},
      el("div", {}, el("strong", {}, g.Nombre), el("div", { class: "meta" }, `${g.Grupo || "sin grupo"} · ${g.Correo}`)),
      el("div", { class: "semanas" }, semanas(g.semanas)),
      el("button", { class: "ir-ficha", type: "button", onclick: () => irAFicha(g.Correo) }, "Ver ficha →")))));
}

function cerrarDetalle() {
  document.querySelectorAll(".cajon, .fondo-cajon").forEach((n) => n.remove());
}

/**
 * Abre el panel lateral con las casillas que hay detrás de lo que se tocó.
 * `lista` reemplaza a la que calcula Python (la franja de la semana, que no
 * usa los filtros) y `excluirItem` saca una semana (la que está en curso).
 */
function abrirDetalle(titulo, criterio, { lista = null, excluirItem = null } = {}) {
  cerrarDetalle();
  let casillas = lista ?? llamar("_casillas", JSON.stringify(criterio));
  if (excluirItem !== null) casillas = casillas.filter((c) => c.Item !== excluirItem);
  const personas = new Set(casillas.map((c) => c.Correo)).size;
  const porAlumno = criterio.estado === "sin_responder";
  let resumen;
  if (porAlumno) {
    // Si a cada uno le falta una sola semana, contar semanas no agrega nada.
    resumen = casillas.length === personas ? plural(personas, "alumno", "alumnos")
      : `${plural(personas, "alumno", "alumnos")} · ${plural(casillas.length, "semana", "semanas")} sin `
        + "responder en total";
  } else {
    const base = casillas.length === personas
      ? plural(casillas.length, "alumno", "alumnos")
      : `${entero(casillas.length)} respuestas de ${plural(personas, "alumno", "alumnos")}`;
    const conNota = casillas.some((c) => hay(c.Nota));
    resumen = [base, conNota ? "de menor a mayor nota" : null].filter(Boolean).join(" · ");
  }
  const cerrar = el("button", { class: "cerrar", type: "button", onclick: cerrarDetalle }, "Cerrar");
  const fondo = el("div", { class: "fondo-cajon", onclick: cerrarDetalle });
  const cajon = el("aside", { class: "cajon", role: "dialog", "aria-label": titulo },
    el("header", {}, el("div", {}, el("h2", {}, titulo), el("p", {}, resumen)), cerrar),
    el("div", { class: "lista" },
      !casillas.length ? el("p", { class: "tenue" }, "No hay casillas con ese criterio.")
        : porAlumno ? listaPorAlumno(casillas) : casillas.map(tarjetaCasilla)));
  document.body.append(fondo, cajon);
  cerrar.focus();
}

document.addEventListener("keydown", (e) => { if (e.key === "Escape") cerrarDetalle(); });

// ---------------------------------------------------------------- secciones

function seccionCurso() {
  const porItem = calc("por_item");
  if (!porItem.length) return [caja("info", "Todavía no hay datos para graficar.")];

  const enCurso = porItem.some((f) => f.Item === itemEnCurso()) ? itemEnCurso() : null;
  const verSemana = (d) => abrirDetalle(`Semana ${d.Item}`, { item: d.Item });
  const verSinResponder = (d) => abrirDetalle(`Semana ${d.Item} · sin responder`,
    { item: d.Item, estado: "sin_responder" });
  const dominio = dominioNotas(porItem.map((f) => f.NotaMedia));
  const g1 = linea(porItem, "NotaMedia", "Nota media", { dominio, alClic: verSemana });
  const g2 = linea(porItem, "TasaRespuesta", "% que respondió", { dominio: [0, 100], alClic: verSinResponder, enCurso });
  const sinNotas = porItem.filter((f) => !hay(f.NotaMedia)).map((f) => f.Item);

  const dist = calc("distribucion_notas");
  const g3 = dist.length ? grafico({
    height: ALTO, data: { values: dist }, mark: "bar",
    encoding: {
      x: campo("Etiqueta", "ordinal", { title: "Nota", sort: dist.map((d) => d.Etiqueta) }),
      y: campo("Alumnos", "quantitative", { title: "Evaluaciones" }),
      tooltip: [{ field: "Etiqueta", title: "Nota" }, { field: "Alumnos", title: "Evaluaciones" }],
    },
  }, (d) => abrirDetalle(`Nota ${d.Etiqueta}`, { tramo: d.Tramo, estado: "evaluada" }))
    : el("p", { class: "tenue" }, "Sin notas para distribuir.");

  const orig = calc("distribucion_originalidad");
  const g4 = orig.length ? grafico({
    height: ALTO, data: { values: orig }, mark: "bar",
    encoding: {
      x: campo("Originalidad", "ordinal", { title: "", sort: orig.map((d) => d.Originalidad) }),
      y: campo("Evaluaciones", "quantitative"),
      color: campo("Originalidad", "nominal", { scale: escalaOriginalidad(orig).escala, legend: null }),
      tooltip: tooltips(["Originalidad", "Evaluaciones"]),
    },
  }, (d) => abrirDetalle(`Originalidad ${d.Originalidad}`, { originalidad: d.Originalidad }))
    : el("p", { class: "tenue" }, "Sin datos de originalidad.");

  const pieNotas = sinNotas.length
    ? `${sinNotas.length === 1 ? "Semana" : "Semanas"} ${sinNotas.join(", ")} sin notas todavía.` : null;
  const pieTasa = enCurso ? `Semana ${enCurso} (punto hueco): aún sin evaluar.` : null;

  return [
    el("div", { class: "grilla2" },
      tarjeta("Nota media por semana", g1 || el("p", { class: "tenue" }, "Sin notas todavía."),
        { pie: pieNotas }),
      tarjeta("Tasa de respuesta por semana", g2 || el("p", { class: "tenue" }, "Sin envíos todavía."),
        { pie: pieTasa })),
    el("div", { class: "grilla2" },
      tarjeta("Distribución de notas", g3),
      tarjeta("Originalidad según el modelo", g4)),
    desplegable("Ver la tabla por semana", tabla(porItem)),
  ];
}

function seccionOriginalidad() {
  const acumulado = calc("distribucion_originalidad");
  if (!acumulado.length) {
    return [caja("info", "Ninguna evaluación de este corte trae categoría de originalidad.")];
  }
  const c = colores();
  const { etiquetas, escala } = escalaOriginalidad(acumulado);
  const corr = calc("correlacion_originalidad_nota");
  const total = acumulado.reduce((s, x) => s + x.Evaluaciones, 0);

  const kpis = el("div", { class: "kpis k4" },
    kpi({ etiqueta: "Evaluaciones con categoría", valor: entero(total) }),
    kpi({ etiqueta: "Nivel medio", valor: numero(corr.NivelMedio, 2), sub: "de 1 (Muy Baja) a 5 (Muy Alta)" }),
    kpi({ etiqueta: "Nota media de esas casillas", valor: numero(corr.NotaMedia, 2) }),
    kpi({ etiqueta: "Correlación con la nota", valor: hay(corr.R) ? numero(corr.R, 3) : null,
      sub: "de rangos, de −1 a 1" }));

  const porItem = calc("originalidad_por_item");
  const vistos = new Set();
  const nivelMedio = porItem.filter((f) => {
    if (f.NivelMedio === null || vistos.has(f.Item)) return false;
    vistos.add(f.Item);
    return true;
  }).map((f) => ({ Item: f.Item, NivelMedio: f.NivelMedio }));

  const gLinea = nivelMedio.length >= 2 ? grafico({
    height: ALTO, data: { values: nivelMedio },
    mark: { type: "line", point: true, strokeWidth: 2, color: rampa()[4] },
    encoding: {
      x: campo("Item", "ordinal", { title: "Semana", sort: nivelMedio.map((f) => f.Item) }),
      y: campo("NivelMedio", "quantitative", { title: "Nivel (1 a 5)", scale: { domain: [1, 5] } }),
      tooltip: tooltips(["Item", "NivelMedio"]),
    },
  }, (d) => abrirDetalle(`Semana ${d.Item}`, { item: d.Item, estado: "evaluada" }))
    : el("p", { class: "tenue" }, "Hace falta más de una semana para ver la evolución.");

  const itemsOrden = [...new Set(porItem.map((f) => f.Item))];
  const gComposicion = porItem.length ? grafico({
    height: ALTO, data: { values: porItem },
    mark: { type: "bar", stroke: c.caja, strokeWidth: 2 },
    encoding: {
      x: campo("Item", "ordinal", { title: "Semana", sort: itemsOrden }),
      y: campo("Porcentaje", "quantitative", {
        title: "% de las evaluadas esa semana", stack: "normalize", axis: { format: "%" } }),
      color: campo("Originalidad", "nominal", { scale: escala, sort: etiquetas, title: "Originalidad" }),
      order: campo("Nivel", "quantitative"),
      tooltip: tooltips(["Item", "Originalidad", "Evaluaciones", "Porcentaje"]),
    },
  }, (d) => abrirDetalle(`Semana ${d.Item} · originalidad ${d.Originalidad}`,
    { item: d.Item, originalidad: d.Originalidad })) : null;

  const vsNota = calc("originalidad_vs_nota");
  const gVsNota = vsNota.length ? grafico({
    height: 240, data: { values: vsNota },
    mark: { type: "bar", cornerRadiusTopLeft: 4, cornerRadiusTopRight: 4 },
    encoding: {
      x: campo("Originalidad", "ordinal", { title: "", sort: etiquetas }),
      y: campo("NotaMedia", "quantitative", { title: "Nota media", scale: { domain: [1.0, 7.0] } }),
      color: campo("Originalidad", "nominal", { scale: escala, sort: etiquetas, legend: null }),
      tooltip: tooltips(["Originalidad", "Evaluaciones", "NotaMedia", "NotaMin", "NotaMax"]),
    },
  }, (d) => abrirDetalle(`Originalidad ${d.Originalidad}`, { originalidad: d.Originalidad })) : null;

  return [
    kpis,
    el("div", { class: "grilla2" },
      tarjeta("Nivel medio de originalidad por semana", gLinea),
      tarjeta("Composición por semana", gComposicion)),
    tarjeta("Nota media según la originalidad que se le vio", gVsNota, {
      pie: "Cuántas evaluaciones hay detrás de cada barra: en la tabla de abajo.",
    }),
    el("hr"),
    el("div", { class: "grilla2" },
      el("div", {}, el("h4", {}, "Acumulado del corte"),
        tabla(acumulado, ["Originalidad", "Evaluaciones", "Porcentaje"])),
      el("div", {}, el("h4", {}, "Originalidad contra nota"),
        tabla(vsNota, ["Originalidad", "Evaluaciones", "NotaMedia", "NotaMin", "NotaMax"]))),
    desplegable("Ver el detalle por semana", tabla(porItem)),
  ];
}

function seccionGrupos() {
  const pg = calc("por_grupo");
  const distintos = new Set(pg.map((f) => f.Grupo));
  if (!pg.length || distintos.size < 2) {
    return [
      caja("info", "Este semestre no tiene dos grupos."),
      pg.length ? tabla(pg) : null,
    ];
  }

  const c = colores();
  const itemsOrden = [...new Set(pg.map((f) => f.Item))];
  const enCurso = itemsOrden.includes(itemEnCurso()) ? itemEnCurso() : null;
  const porGrupo = (y, tituloEje, dominio) => {
    const sub = pg.filter((f) => hay(f[y]));
    if (!sub.length) return el("p", { class: "tenue" }, "Sin datos.");
    return grafico({
      height: ALTO, data: { values: sub }, mark: { type: "line", point: true },
      encoding: {
        x: campo("Item", "ordinal", { title: "Semana", sort: itemsOrden, scale: { domain: itemsOrden } }),
        y: campo(y, "quantitative", { title: tituloEje, scale: { domain: dominio } }),
        color: campo("Grupo", "nominal", { title: "Grupo" }),
        tooltip: tooltips(["Item", "Grupo", "NotaMedia", "TasaRespuesta", "Evaluados"]),
      },
    }, (d) => abrirDetalle(`Semana ${d.Item} · ${d.Grupo}`, { item: d.Item, grupo: d.Grupo }));
  };

  // La diferencia entre brazos es el número que interesa del estudio. Es solo
  // un reacomodo de las filas de por_grupo para el gráfico, como el pivot de main.py.
  const pivote = itemsOrden.map((item) => {
    const fc = pg.find((f) => f.Item === item && f.Grupo === "control");
    const ft = pg.find((f) => f.Item === item && f.Grupo === "tratamiento");
    const control = fc ? fc.NotaMedia : null;
    const tratamiento = ft ? ft.NotaMedia : null;
    const Diferencia = control !== null && tratamiento !== null
      ? Math.round((tratamiento - control) * 100) / 100 : null;
    return { Item: item, control, tratamiento, Diferencia };
  }).filter((f) => f.Diferencia !== null);

  const gDif = distintos.has("control") && distintos.has("tratamiento") && pivote.length ? grafico({
    height: 200, data: { values: pivote },
    mark: "bar",
    encoding: {
      x: campo("Item", "ordinal", { title: "Semana", sort: itemsOrden }),
      y: campo("Diferencia", "quantitative", { title: "Puntos de nota" }),
      color: { condition: { test: "datum.Diferencia > 0", value: c.ok }, value: c.rojo },
      tooltip: tooltips(["Item", "control", "tratamiento", "Diferencia"]),
    },
  }, (d) => abrirDetalle(`Semana ${d.Item} · los dos grupos`, { item: d.Item, estado: "evaluada" })) : null;

  return [
    el("div", { class: "grilla2" },
      tarjeta("Nota media por grupo", porGrupo("NotaMedia", "Nota media", dominioNotas(pg.map((f) => f.NotaMedia)))),
      tarjeta("Tasa de respuesta por grupo", porGrupo("TasaRespuesta", "% que respondió", [0, 100]), {
        pie: enCurso ? `Semana ${enCurso}: aún sin evaluar.` : null,
      })),
    tarjeta("Diferencia de nota (Tratamiento − Control)", gDif, {
      pie: "Sobre cero, mejor nota media en Tratamiento.",
    }),
    desplegable("Ver la tabla por grupo", tabla(pg)),
  ];
}

// ---------------------------------------------------------------- correlaciones

const UNIDADES = [["alumno", "Por alumno"], ["respuesta", "Por respuesta"]];

/** Mezcla dos colores #rrggbb: t = 0 da el primero y t = 1 el segundo. */
function mezcla(a, b, t) {
  const canal = (hex, i) => parseInt(hex.slice(1 + 2 * i, 3 + 2 * i), 16);
  return `#${[0, 1, 2].map((i) => Math.round(canal(a, i) + (canal(b, i) - canal(a, i)) * t)
    .toString(16).padStart(2, "0")).join("")}`;
}

/**
 * El número del par elegido. Por respuesta no lleva intervalo: las de un mismo
 * alumno se parecen entre sí y saldría más angosto de lo que es.
 */
function lecturaCorrelacion(celda, porAlumno) {
  if (!celda || !hay(celda.R)) return "Sin datos suficientes.";
  const partes = [`r = ${numero(celda.R, 2)}`,
    plural(celda.N, porAlumno ? "alumno" : "respuesta", porAlumno ? "alumnos" : "respuestas")];
  if (porAlumno && hay(celda.Bajo)) partes.push(`IC 95 %: ${numero(celda.Bajo, 2)} a ${numero(celda.Alto, 2)}`);
  return partes.join(" · ");
}

function seccionCorrelaciones() {
  const cfg = estado.correlacion;
  const porAlumno = cfg.unidad === "alumno";
  const m = calc(porAlumno ? "correlaciones_por_alumno" : "correlaciones_por_respuesta");
  const unidad = el("div", { class: "chips", role: "group", "aria-label": "Unidad" }, UNIDADES.map(([id, texto]) =>
    el("button", {
      class: "chip", type: "button", "aria-pressed": String(cfg.unidad === id),
      onclick: () => { cfg.unidad = id; dibujarPestana(); },
    }, texto)));
  if (m.Variables.length < 2) {
    return [unidad, caja("info", "Este corte no tiene datos suficientes para calcular correlaciones.")];
  }

  const campos = m.Variables.map((v) => v.Campo);
  const etiqueta = Object.fromEntries(m.Variables.map((v) => [v.Campo, v.Etiqueta]));
  // El par elegido, si sigue existiendo en este corte; si no, el primero de la tabla.
  let [x, y] = cfg[cfg.unidad];
  let celda = m.Celdas.find((c) => (c.X === x && c.Y === y) || (c.X === y && c.Y === x));
  if (!celda) celda = m.Celdas[0];
  [x, y] = [celda.X, celda.Y];
  cfg[cfg.unidad] = [x, y];

  const c = colores();
  const elegida = `datum.X === ${JSON.stringify(x)} && datum.Y === ${JSON.stringify(y)}`;
  // El tono sale del fondo de la tarjeta hacia azul o rojo según |r|: cerca de
  // cero el cuadro casi no se tiñe, en los dos temas.
  const celdas = m.Celdas.map((d) => {
    const fuerza = hay(d.R) ? Math.min(1, Math.abs(d.R)) : 0;
    return {
      ...d,
      Texto: hay(d.R) ? numero(Math.abs(d.R) < 0.005 ? 0 : d.R, 2) : "—",
      Color: hay(d.R) ? mezcla(c.caja, d.R >= 0 ? c.acento : c.rojo, fuerza) : c.linea,
      ColorTexto: fuerza > 0.55 ? c.caja : c.texto,
    };
  });
  const ordenX = m.Variables.slice(0, -1).map((v) => v.Etiqueta);
  const ordenY = m.Variables.slice(1).map((v) => v.Etiqueta);
  const gMatriz = grafico({
    height: 46 * ordenY.length, data: { values: celdas },
    encoding: {
      // Partidas en líneas, o giradas en el celular: en una sola línea, las
      // etiquetas vecinas se pisan.
      x: campo("EtiquetaX", "ordinal", { title: null, sort: ordenX,
        axis: MEDIA_ANGOSTA.matches
          ? { labelAngle: -40, labelAlign: "right", labelOverlap: false }
          : { labelAngle: 0, labelOverlap: false, labelExpr: "split(datum.label, ' ')" } }),
      y: campo("EtiquetaY", "ordinal", { title: null, sort: ordenY, axis: { labelLimit: 140 } }),
      tooltip: tooltips(["EtiquetaX", "EtiquetaY", "R", "N"]),
    },
    layer: [
      {
        mark: { type: "rect", cornerRadius: 4 },
        encoding: {
          color: campo("Color", "nominal", { scale: null }),
          stroke: { condition: { test: elegida, value: c.texto }, value: c.linea },
          strokeWidth: { condition: { test: elegida, value: 2.5 }, value: 1 },
        },
      },
      {
        mark: { type: "text", fontSize: 13 },
        encoding: {
          text: campo("Texto", "nominal"),
          color: campo("ColorTexto", "nominal", { scale: null }),
        },
      },
    ],
  }, (d) => { cfg[cfg.unidad] = [d.X, d.Y]; dibujarPestana(); });

  const puntos = m.Puntos.filter((p) => hay(p[x]) && hay(p[y]));
  const gPuntos = grafico({
    height: ALTO, data: { values: puntos },
    encoding: {
      x: campo(x, "quantitative", { title: etiqueta[x], scale: { zero: false } }),
      y: campo(y, "quantitative", { title: etiqueta[y], scale: { zero: false } }),
    },
    layer: [
      {
        mark: { type: "point", filled: true, size: 55, opacity: 0.75 },
        encoding: {
          color: campo("Grupo", "nominal", { title: "Grupo" }),
          tooltip: tooltips(porAlumno ? ["Nombre", "Grupo", x, y] : ["Nombre", "Item", x, y]),
        },
      },
      {
        transform: [{ regression: y, on: x }],
        mark: { type: "line", color: c.tenue, strokeDash: [5, 4] },
      },
    ],
  }, (d) => { if (d.Correo) irAFicha(d.Correo); });

  const todas = m.Celdas.map((d) => ({
    "Variable 1": etiqueta[d.X], "Variable 2": etiqueta[d.Y], r: hay(d.R) ? numero(d.R, 2) : "—", n: d.N,
    ...(porAlumno ? { "Intervalo 95 %": hay(d.Bajo) ? `${numero(d.Bajo, 2)} a ${numero(d.Alto, 2)}` : "—" } : {}),
  }));

  return [
    unidad,
    el("div", { class: "grilla2" },
      tarjeta("Correlación (Pearson)", gMatriz),
      el("div", { class: "tarjeta" },
        el("h3", { class: "titulo-grafico" }, `${etiqueta[x]} y ${etiqueta[y]}`),
        gPuntos,
        el("p", { class: "pie-grafico" }, lecturaCorrelacion(celda, porAlumno)))),
    campos.includes("Tratamiento")
      ? el("p", { class: "nota-pie" }, "Tratamiento: 1 en ese grupo, 0 en control.") : null,
    desplegable("Ver la tabla", tabla(todas)),
  ];
}

// Columnas de la tabla de alumnos: nombre legible y cómo se muestra cada una.
const COLS_ALUMNOS = [
  // Las "secundarias" no se muestran en el celular, para que la nota quede a la vista.
  { campo: "Nombre", titulo: "Alumno", tipo: "texto" },
  { campo: "Grupo", titulo: "Grupo", tipo: "texto", secundaria: true },
  { campo: "NotaMedia", titulo: "Nota media", tipo: "nota" },
  { campo: "TasaRespuesta", titulo: "% de respuesta", tipo: "pct" },
  { campo: "Respondieron", titulo: "Respondió", tipo: "n", secundaria: true },
  { campo: "Evaluados", titulo: "Con nota", tipo: "n", secundaria: true },
  { campo: "SinResponder", titulo: "Sin responder", tipo: "n" },
  { campo: "NotaMin", titulo: "Nota mín.", tipo: "nota", secundaria: true },
  { campo: "NotaMax", titulo: "Nota máx.", tipo: "nota", secundaria: true },
];

/** Compara dos valores de una columna; los vacíos van siempre al final. */
function compararAlumnos(a, b, col, asc) {
  const x = a[col.campo], y = b[col.campo];
  if (!hay(x) || !hay(y)) return hay(x) ? -1 : hay(y) ? 1 : 0;
  const r = col.tipo === "texto" ? String(x).localeCompare(String(y), "es") : x - y;
  return (asc ? r : -r) || a.Nombre.localeCompare(b.Nombre, "es");
}

function celdaAlumno(a, col) {
  const v = a[col.campo];
  const clase = [col.tipo === "texto" ? null : "num", col.secundaria ? "secundaria" : null].filter(Boolean).join(" ") || null;
  if (col.campo === "Nombre") {
    return el("td", {}, el("span", { class: "nombre" }, v), el("span", { class: "correo" }, a.Correo));
  }
  const texto = col.tipo === "nota" ? numero(v, 1)
    : col.tipo === "pct" ? (hay(v) ? `${numero(v, 1)} %` : "—")
      : col.tipo === "n" ? entero(v) : (v || "—");
  return el("td", { class: clase }, texto);
}

function seccionAlumnos() {
  const pa = calc("por_alumno");
  if (!pa.length) return [caja("info", "Sin alumnos que mostrar con estos filtros.")];

  if (!estado.alumno || !pa.some((a) => a.Correo === estado.alumno)) estado.alumno = pa[0].Correo;

  const cabeza = el("tr");
  const cuerpo = el("tbody");
  const cuenta = el("span", { class: "tenue" });
  const fichaNodo = el("section", { class: "ficha", "aria-label": "Ficha del alumno" });
  const buscador = el("input", {
    type: "search", class: "buscador", placeholder: "Buscar por nombre o correo",
    "aria-label": "Buscar alumno", value: estado.busquedaAlumnos,
  });
  buscador.addEventListener("input", () => { estado.busquedaAlumnos = buscador.value; pintarFilas(); });

  // Sin un orden elegido se respeta el de Python: de la nota media más baja a la más alta.
  const visibles = () => {
    const q = normalizar(estado.busquedaAlumnos.trim());
    const filas = pa.filter((a) => !q || normalizar(`${a.Nombre} ${a.Correo}`).includes(q));
    const o = estado.ordenAlumnos;
    if (!o) return filas;
    const col = COLS_ALUMNOS.find((c) => c.campo === o.campo);
    return [...filas].sort((a, b) => compararAlumnos(a, b, col, o.asc));
  };

  function pintarCabeza() {
    const o = estado.ordenAlumnos || { campo: "NotaMedia", asc: true };
    cabeza.replaceChildren(...COLS_ALUMNOS.map((col) => {
      const activa = o.campo === col.campo;
      return el("th", {
        class: [col.tipo === "texto" ? null : "num", col.secundaria ? "secundaria" : null].filter(Boolean).join(" ") || null,
        "aria-sort": activa ? (o.asc ? "ascending" : "descending") : null,
      }, el("button", {
        class: "orden", type: "button",
        onclick: () => {
          estado.ordenAlumnos = { campo: col.campo, asc: activa ? !o.asc : true };
          pintarCabeza();
          pintarFilas();
        },
      }, col.titulo, el("span", { class: "flecha-orden", "aria-hidden": "true" }, activa ? (o.asc ? " ▲" : " ▼") : "")));
    }));
  }

  function pintarFilas() {
    const filas = visibles();
    cuenta.textContent = filas.length === pa.length
      ? plural(pa.length, "alumno", "alumnos") : `${filas.length} de ${plural(pa.length, "alumno", "alumnos")}`;
    cuerpo.replaceChildren(...(filas.length ? filas.map((a) => el("tr", {
      tabindex: "0", "data-correo": a.Correo, "aria-selected": String(a.Correo === estado.alumno),
      onclick: () => elegir(a.Correo, true),
      onkeydown: (e) => { if (e.key === "Enter") elegir(a.Correo, true); },
    }, COLS_ALUMNOS.map((col) => celdaAlumno(a, col))))
      : [el("tr", {}, el("td", { colspan: String(COLS_ALUMNOS.length), class: "tenue" }, "Nadie coincide con la búsqueda."))]));
  }

  function elegir(correo, desplazar) {
    estado.alumno = correo;
    cuerpo.querySelectorAll("tr[data-correo]").forEach((tr) => {
      tr.setAttribute("aria-selected", String(tr.dataset.correo === correo));
    });
    fichaNodo.replaceChildren(...fichaAlumno(correo));
    if (desplazar) fichaNodo.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  pintarCabeza();
  pintarFilas();
  fichaNodo.replaceChildren(...fichaAlumno(estado.alumno));
  if (estado.irAFicha) {
    estado.irAFicha = false;
    requestAnimationFrame(() => fichaNodo.scrollIntoView({ block: "start" }));
  }

  return [
    el("div", { class: "barra-alumnos" }, buscador, cuenta),
    el("div", { class: "tabla-envoltura" },
      el("table", { class: "alumnos" }, el("thead", {}, cabeza), cuerpo)),
    el("hr"),
    fichaNodo,
  ];
}

function fichaAlumno(correo) {
  const f = llamar("_ficha_todas", correo);
  if (!f || !f.Resumen) return [el("p", { class: "tenue" }, "No hay datos de este alumno.")];
  const r = f.Resumen;
  const partes = [
    el("h3", { class: "titulo-ficha" }, `Ficha de ${f.Nombre}`),
    el("p", { class: "nota-pie" }, `${f.Correo} · grupo ${f.Grupo || "sin grupo"}`),
    el("div", { class: "kpis k3" },
      kpi({ etiqueta: "Nota media", valor: numero(r.NotaMedia, 1),
        sub: hay(r.NotaMin) ? `mín ${numero(r.NotaMin)} · máx ${numero(r.NotaMax)}` : null }),
      kpi({ etiqueta: "Respondió", valor: `${r.Respondieron} de ${r.Enviados}`, sub: "semanas que la recibió" }),
      kpi({ etiqueta: "Con nota", valor: entero(r.Evaluados) })),
  ];

  const serie = f.Casillas.filter((c) => hay(c.Nota));
  if (serie.length >= 2) {
    partes.push(tarjeta("Sus notas por semana", grafico({
      height: 220, data: { values: serie },
      mark: { type: "line", point: true },
      encoding: {
        x: campo("Item", "ordinal", { title: "Semana", sort: f.Casillas.map((c) => c.Item) }),
        y: campo("Nota", "quantitative", { scale: { domain: dominioNotas(serie.map((c) => c.Nota)) } }),
        tooltip: tooltips(["Item", "Nota", "Originalidad"]),
      },
    })));
  }

  partes.push(el("h4", {}, "Semana a semana"));
  // Si arriba se eligieron algunas semanas (no todas), esas parten abiertas.
  const elegidas = estado.selItems.size && estado.selItems.size < estado.items.length ? estado.selItems : null;
  const grupo = f.Grupo === "tratamiento" ? "tratamiento" : "control";
  for (const c of f.Casillas) {
    const est = c.NotaTexto ? `nota ${c.NotaTexto}` : c.Respondio ? "respondió, sin evaluar"
      : c.Item === itemEnCurso() ? "semana en curso, aún sin evaluar" : "sin responder";
    const semana = estado.preguntas ? leerSemana(estado.preguntas, Number(c.Item)) : null;
    const enunciados = semana ? semana.preguntas.map((p) => p[grupo].texto).filter((x) => x.trim()) : [];
    partes.push(el("details", { open: Boolean(elegidas && elegidas.has(c.Item)) },
      el("summary", {}, `Semana ${c.Item} — ${est}`),
      el("div", { class: "contenido" },
      enunciados.length
        ? [el("p", {}, el("strong", {}, "Lo que se le preguntó")),
          el("ol", { class: "enunciados" }, enunciados.map((x) => el("li", {}, x)))]
        : null,
      c.Respuesta
        ? [el("p", {}, el("strong", {}, "Lo que respondió")), el("div", { class: "respuesta" }, c.Respuesta)]
        : el("p", { class: "tenue" }, "No hay texto de respuesta guardado."),
      c.EvaluacionIA
        ? [el("p", {}, el("strong", {}, "El correo que recibió")), correoEvaluacion({ ...c, Nombre: f.Nombre, Correo: f.Correo })]
        : null,
      c.Modelo ? el("p", { class: "tenue" }, `Modelo: ${c.Modelo}`) : null,
      c.Respondio || c.NotaTexto ? formularioAjuste(c) : null)));
  }
  return partes;
}

/**
 * Cambiar la nota a mano cuando el modelo se equivocó. Queda en el log con el
 * motivo, la nota anterior y quién lo hizo, y no se le escribe al alumno
 * (modulos/datos/ajustar.py).
 */
function formularioAjuste(c) {
  const nota = el("input", { type: "text", size: 5, placeholder: "6,5", "aria-label": "Nota nueva" });
  const motivo = el("input", { type: "text", size: 40, placeholder: "opcional", "aria-label": "Motivo (opcional)" });
  const destino = el("div");
  const boton = el("button", { class: "descarga", type: "button" }, "Guardar ajuste");
  boton.addEventListener("click", async () => {
    const n = nota.value.trim().replace(".", ",");
    if (!/^\d{1,2}(,\d)?$/.test(n) || Number(n.replace(",", ".")) > 7) {
      destino.replaceChildren(caja("aviso", "La nota se escribe como 6,5 (entre 1,0 y 7,0)."));
      return;
    }
    if (!confirm(`Cambiar la nota de ${c.Nombre}, semana ${c.Item}: ${c.NotaTexto || "sin nota"} → ${n}.
`
      + "No se le envía ningún correo. ¿Confirmas?")) return;
    boton.disabled = true;
    try {
      const id = await pedirTrabajo(estado.semestre, "datos.ajustar",
        { flujo: "test", item: String(c.Item), correo: c.Correo, nota: n, motivo: motivo.value.trim() });
      await seguirTrabajo(id, destino, {
        alTerminar: (t) => {
          boton.disabled = false;
          if (t.estado === "terminado") {
            destino.append(el("button", { class: "enlace", type: "button", onclick: () => location.reload() },
              "Recargar para ver la nota nueva"));
          }
        },
      });
    } catch (e) {
      boton.disabled = false;
      destino.replaceChildren(caja("aviso", `No pude pedir el ajuste: ${e.message}`));
    }
  });
  return el("details", { class: "ajuste" }, el("summary", {}, "Ajustar nota a mano"),
    el("div", { class: "contenido" },
      el("p", { class: "nota-pie" }, "Queda registrado, con el motivo si lo escribes. No se envía correo."),
      el("div", { class: "fila-campos" }, el("label", { class: "campo" }, "Nota nueva", nota),
        el("label", { class: "campo" }, "Motivo (opcional)", motivo), boton),
      destino));
}

function seccionPendientes() {
  // Las listas salen de casillas(), con el mismo criterio que usan los conteos
  // sin_responder() y pendientes_de_evaluar(); la prueba web.py vigila que
  // coincidan. Así se pueden desplegar y leer ahí mismo.
  const enCurso = itemEnCurso();
  const sinResp = llamar("_casillas", JSON.stringify({ estado: "sin_responder" }));
  const pend = llamar("_casillas", JSON.stringify({ estado: "sin_nota" }));
  const cerradas = sinResp.filter((c) => c.Item !== enCurso);
  const deEnCurso = sinResp.filter((c) => c.Item === enCurso);
  return [
    el("h4", {}, `Respondieron pero no tienen nota — ${pend.length}`),
    pend.length ? [
      el("p", { class: "nota-pie" }, "Pueden ser respuestas fuera de plazo. Se evalúan en ",
        el("a", { href: "/tests#evaluar" }, "Tests Semanales › Evaluar respuestas"), "."),
      pend.map(tarjetaCasilla),
    ] : caja("exito", "No hay respuestas pendientes de evaluación."),
    el("hr"),
    el("h4", {}, `${deEnCurso.length ? "Sin responder en semanas ya evaluadas" : "Sin responder"} — ${cerradas.length}`),
    cerradas.length ? listaPorAlumno(cerradas) : caja("exito", "Todos respondieron lo que se les envió."),
    deEnCurso.length ? desplegable(`Semana ${enCurso}, aún sin evaluar: ${plural(deEnCurso.length, "alumno", "alumnos")} `
      + "sin respuesta registrada (puede estar en el buzón)", listaPorAlumno(deEnCurso)) : null,
  ];
}

function seccionDescargar() {
  return [
    el("section", { class: "opcion-descarga" },
      el("h3", {}, "Datos de esta página"),
      el("p", { class: "nota-pie" }, "Una fila por alumno y semana, con los filtros de arriba."),
      el("button", { class: "descarga", type: "button", onclick: descargarCsv }, "Descargar estos datos (CSV)")),
    el("hr"),
    sabanaDe(estado.semestre),
  ];
}

const SECCIONES = {
  Curso: seccionCurso, Originalidad: seccionOriginalidad, Grupos: seccionGrupos, Correlaciones: seccionCorrelaciones,
  Alumnos: seccionAlumnos, Pendientes: seccionPendientes, Descargar: seccionDescargar,
};

// ---------------------------------------------------------------- pantalla

// La sección de la sábana se arma una vez por semestre: la reportería se
// redibuja con cada filtro, y rehacerla bajaría el CSV completo cada vez.
let sabana = { semestre: null, nodo: null };
function sabanaDe(semestre) {
  if (sabana.semestre !== semestre) sabana = { semestre, nodo: seccionSabana(semestre) };
  return sabana.nodo;
}

function descargarCsv() {
  const filas = llamar("_vista");
  if (!filas.length) return;
  const cols = Object.keys(filas[0]);
  descargar(`panel_${estado.semestre}_tests.csv`, exportarCsv(cols, filas.map((f) => cols.map((c) => f[c]))));
}

// Un clic marca o desmarca; dos clics seguidos dejan solo esa. Se espera un
// momento antes de aplicar el primero: si se redibujara al tiro, el segundo clic
// caería en otro botón.
let clicPendiente = null;
function chips(opciones, seleccion) {
  const todas = opciones.length && opciones.every((o) => seleccion.has(o));
  const alternar = el("button", {
    class: "chip alternar", type: "button",
    onclick: () => {
      if (todas) seleccion.clear(); else opciones.forEach((o) => seleccion.add(o));
      dibujar();
    },
  }, todas ? "Ninguna" : "Todas");
  return el("div", { class: "chips" }, alternar, opciones.map((o) => el("button", {
    class: "chip", type: "button", "aria-pressed": String(seleccion.has(o)), title: "Doble clic: solo esta",
    onclick: () => {
      if (clicPendiente && clicPendiente.o === o && clicPendiente.seleccion === seleccion) {
        clearTimeout(clicPendiente.reloj);
        clicPendiente = null;
        seleccion.clear();
        seleccion.add(o);
        dibujar();
        return;
      }
      const reloj = setTimeout(() => {
        clicPendiente = null;
        if (seleccion.has(o)) seleccion.delete(o); else seleccion.add(o);
        dibujar();
      }, 250);
      clicPendiente = { o, seleccion, reloj };
    },
  }, o)));
}

let contenedorPestana = null;

function dibujarPestana() {
  if (!contenedorPestana) return;
  contenedorPestana.replaceChildren(...[SECCIONES[estado.pestana]()].flat(Infinity).filter(Boolean));
}

/**
 * Cuándo se subieron los datos que se ven, siempre a la vista. Con más de dos
 * días pasa a aviso: lo más reciente puede no estar.
 */
function fechaDatos(sem) {
  const d = fechaValida(sem && sem.actualizado);
  if (d) {
    const texto = `Datos al ${fechaHora(d)} (${haceCuanto(sem.actualizado)})`;
    return Date.now() - d.getTime() > 48 * 3600e3
      ? caja("aviso fecha-vieja", `${texto}: puede faltar lo más reciente.`)
      : el("p", { class: "fecha-datos" }, texto);
  }
  // Sin fecha de subida (un semestre subido antes de que se guardara), al menos
  // se dice hasta cuándo llega lo que traen.
  const ultima = estado.filas.flatMap((f) => [f.FechaRespuesta, f.FechaEnvio])
    .map(fechaValida).filter(Boolean).sort((a, b) => b - a)[0];
  return el("p", { class: "fecha-datos" }, ultima
    ? `Datos hasta el ${fechaHora(ultima)}` : "");
}

function textoFiltros() {
  const sem = estado.selItems.size && estado.selItems.size < estado.items.length
    ? `${estado.selItems.size} de ${estado.items.length} semanas` : "todas las semanas";
  const gru = estado.selGrupos.size && estado.selGrupos.size < estado.grupos.length
    ? [...estado.selGrupos].join(", ") : "todos los grupos";
  return `Filtros: ${sem} · ${gru}`;
}

function dibujar() {
  const sem = estado.semestres.find((x) => x.id === estado.semestre);
  const cabecera = el("div", { class: "cabecera" },
    el("div", {},
      el("label", { for: "semestre" }, "Semestre"),
      el("select", {
        id: "semestre",
        onchange: async (e) => { await cargarSemestre(e.target.value); dibujar(); },
      }, estado.semestres.map((s) => el("option", { value: s.id, selected: s.id === estado.semestre }, s.id)))),
    fechaDatos(sem),
    estado.activo && estado.semestre !== estado.activo
      ? caja("aviso semestre-distinto", `Viendo ${estado.semestre}. El semestre activo es ${estado.activo}.`)
      : null);

  // Una selección vacía no filtra, igual que el multiselect de Streamlit: la
  // función filtrar() de Python trata la lista vacía como "sin filtro".
  const n = llamar("_filtrar", JSON.stringify([...estado.selItems]), JSON.stringify([...estado.selGrupos]));

  // En el celular los filtros quedan plegados: si no, llenan la pantalla antes
  // del primer número. En pantallas anchas se ven siempre.
  const angosta = MEDIA_ANGOSTA.matches;
  const filtros = el("details", {
    class: "filtros-plegables", open: angosta ? Boolean(estado.filtrosAbiertos) : true,
    ontoggle: (e) => { if (MEDIA_ANGOSTA.matches) estado.filtrosAbiertos = e.target.open; },
  },
    el("summary", {}, textoFiltros()),
    el("div", { class: "filtros" },
      el("div", { class: "filtro" }, el("span", {}, "Semanas"), chips(estado.items, estado.selItems)),
      el("div", { class: "filtro" }, el("span", {}, "Grupos"), chips(estado.grupos, estado.selGrupos))));

  // La semana en curso y lo que requiere atención están en Inicio: aquí solo los resultados.
  // La sábana se prepara (y se pone al día si hace falta) al abrir la página,
  // aunque no se entre a su pestaña.
  if (estado.semestre && estado.filas.length) sabanaDe(estado.semestre);

  if (!n) {
    app.replaceChildren(cabecera, ...(estado.filas.length
      ? [filtros, caja("aviso", "Los filtros no dejan ninguna fila.")]
      : [caja("info", `${estado.semestre} todavía no tiene datos.`)]));
    return;
  }

  const r = calc("resumen");
  const porItem = calc("por_item");
  // La semana en curso, si está dentro de los filtros: sin evaluar no se sabe
  // quién respondió (las respuestas siguen en el buzón), así que no se junta
  // con los "sin responder" de las semanas ya evaluadas.
  const enCurso = porItem.some((f) => f.Item === itemEnCurso()) ? itemEnCurso() : null;
  const filaEnCurso = enCurso ? porItem.find((f) => f.Item === enCurso) : null;
  const sinRespEnCurso = filaEnCurso ? filaEnCurso.SinResponder : 0;
  const sinRespCerradas = r.SinResponder - sinRespEnCurso;
  const enviadosCerradas = r.Enviados - (filaEnCurso ? filaEnCurso.Enviados : 0);
  const tasaCerradas = filaEnCurso && enviadosCerradas
    ? ((r.Respondieron - filaEnCurso.Respondieron) / enviadosCerradas) * 100 : null;
  // Lo pendiente es lo que el equipo puede resolver: respuestas que esperan nota.
  // Quienes no respondieron se acumulan en el semestre; van en su indicador,
  // no como alerta permanente.
  const nPendientes = r.PendientesEvaluar;

  const nGrupos = estado.selGrupos.size || estado.grupos.length;
  const meta = el("p", { class: "meta-vista" }, [
    plural(r.Alumnos, "alumno", "alumnos"), plural(r.Items, "semana", "semanas"), plural(nGrupos, "grupo", "grupos"),
    r.Modelos && r.Modelos.length ? `evaluadas con ${r.Modelos.join(", ")}` : null,
  ].filter(Boolean).join(" · "));

  const kpis = el("div", { class: "kpis k4" },
    kpi({
      etiqueta: "Tasa de respuesta", valor: hay(r.TasaRespuesta) ? `${numero(r.TasaRespuesta)} %` : null,
      sub: [`respondieron ${entero(r.Respondieron)} de ${entero(r.Enviados)} envíos`,
        hay(tasaCerradas) ? `${numero(tasaCerradas)} % sin contar la semana ${enCurso}, aún sin evaluar` : null],
    }),
    kpi({
      etiqueta: "Nota media", valor: numero(r.NotaMedia, 2),
      sub: hay(r.NotaMin) ? `mín ${numero(r.NotaMin)} · máx ${numero(r.NotaMax)}` : "sin notas todavía",
    }),
    kpi({
      etiqueta: "Evaluadas", valor: entero(r.Evaluados), sub: "respuestas con nota", accion: "ver todas →",
      alClic: () => abrirDetalle("Respuestas evaluadas", { estado: "evaluada" }),
    }),
    // La semana en curso no cuenta: sus respuestas siguen en el buzón hasta
    // evaluarla, así que no se sabe quién respondió.
    kpi({
      etiqueta: "Sin responder", valor: entero(sinRespCerradas),
      sub: sinRespEnCurso
        ? ["en semanas ya evaluadas", `la semana ${enCurso} se cuenta al evaluarla`]
        : "se les envió y no respondieron",
      accion: sinRespCerradas ? "ver quiénes →" : null,
      alClic: sinRespCerradas ? () => abrirDetalle(enCurso ? "Sin responder en semanas ya evaluadas" : "Sin responder",
        { estado: "sin_responder" }, { excluirItem: enCurso }) : null,
    }));

  const notas = [
    r.EnviosSinRegistro ? el("p", { class: "nota-pie" },
      `${r.EnviosSinRegistro} casilla(s) sin registro de envío, enviadas desde otro equipo.`) : null,
  ];

  const pestanas = el("div", { class: "pestanas", role: "tablist" }, PESTANAS.map((p) => el("button", {
    class: "pestana", role: "tab", type: "button", "aria-selected": String(p.id === estado.pestana),
    onclick: () => { estado.pestana = p.id; history.replaceState(null, "", `#${p.id}`); dibujar(); },
  }, p.id === "Pendientes" && nPendientes ? `Pendientes (${entero(nPendientes)})` : (p.etiqueta || p.id))));

  contenedorPestana = el("div", { role: "tabpanel" });
  app.replaceChildren(cabecera, filtros, meta, kpis, ...notas.filter(Boolean), pestanas, contenedorPestana);
  dibujarPestana();
}

// Los gráficos toman los colores al dibujarse: si cambia el tema, se redibujan.
// Al cruzar el ancho de celular, los filtros pasan a plegarse o a verse siempre.
const redibujar = () => { if (py && estado.semestre) dibujar(); };
MEDIA_OSCURO.addEventListener("change", redibujar);
window.addEventListener("cambio-tema", redibujar);
MEDIA_ANGOSTA.addEventListener("change", redibujar);

async function iniciar() {
  // La pestaña va en la dirección (#Grupos), para poder mandar un enlace directo.
  // #Alumnos/<correo> abre directo la ficha de ese alumno (el buscador de Inicio).
  const [pedida, correo] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (PESTANAS.some((p) => p.id === pedida)) estado.pestana = pedida;
  const alumnoPedido = pedida === "Alumnos" && correo ? correo.toLowerCase() : null;
  try {
    app.replaceChildren(el("p", { class: "cargando" }, "Cargando…"));
    const [semestres] = await Promise.all([api("/api/semestres"), iniciarPython()]);
    estado.semestres = semestres;
    if (!semestres.length) {
      app.replaceChildren(caja("aviso", "Todavía no hay datos. Súbelos desde el equipo que opera el curso con: "
        + "python -m modulos.web.subir"));
      return;
    }
    const activo = semestres.find((s) => s.activo);
    estado.activo = activo ? activo.id : null;
    await cargarSemestre(estado.activo || semestres[semestres.length - 1].id);
    if (alumnoPedido) { estado.alumno = alumnoPedido; estado.irAFicha = true; }
    dibujar();
  } catch (e) {
    app.replaceChildren(caja("aviso", `No pude cargar los resultados: ${e.message}`));
  }
}

iniciar();
