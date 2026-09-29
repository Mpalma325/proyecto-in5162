// Reportería del curso: la misma pantalla de inicio de Streamlit, en web.
//
// Los cálculos no están acá. La página carga modulos/datos/agregaciones.py y lo
// corre con Pyodide, así que cada número sale de la misma función de Python que
// usa Streamlit. Este archivo solo trae datos, pide cálculos y dibuja.

import { api, caja, el, navegacion, pedirTrabajo, seguirTrabajo } from "./comun.js";
import { descargar, exportarCsv } from "./csv.js";
import { seccionSabana } from "./sabana.js";

document.getElementById("nav")?.replaceWith(navegacion());

const ALTO = 260;
// Misma rampa que app/main.py: la originalidad es una escala ordenada, así que
// va en un solo tono de claro a oscuro, pegado al nivel y no al orden de aparición.
const RAMPA = ["#d6e4f5", "#a9c7ea", "#6ea8db", "#3d82c4", "#1a5490"];
const SIN_NIVEL = "#9e9e9e";
const PESTANAS = ["Curso", "Originalidad", "Grupos", "Alumnos", "Pendientes"];

const app = document.getElementById("app");
const estado = {
  semestres: [], semestre: null, activo: null,
  items: [], grupos: [], selItems: new Set(), selGrupos: new Set(),
  pestana: "Curso", alumno: null,
};
let py = null;

// ---------------------------------------------------------------- utilidades


const guion = (v) => (v === null || v === undefined ? "—" : v);

function kpi(etiqueta, valor, sufijo = "", ayuda = null, sub = null, alClic = null) {
  return el("div", {
    class: alClic ? "kpi clic" : "kpi", title: ayuda, onclick: alClic,
    role: alClic ? "button" : null, tabindex: alClic ? "0" : null,
  },
    el("div", { class: "etiqueta" }, etiqueta),
    el("div", { class: "valor" }, valor === null || valor === undefined ? "—" : `${valor}${sufijo}`),
    sub ? el("div", { class: "sub" }, sub) : null);
}

/** Un gráfico dentro de su tarjeta, con la indicación de que se puede hacer clic. */
function tarjeta(nodoGrafico, pista = null) {
  if (!nodoGrafico) return null;
  if (!(nodoGrafico instanceof Node) || !nodoGrafico.classList.contains("grafico")) {
    return el("div", { class: "tarjeta" }, nodoGrafico);
  }
  return el("div", { class: "tarjeta" }, nodoGrafico, pista ? el("p", { class: "pista" }, pista) : null);
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

// La evaluación del agente es HTML generado por el modelo a partir del texto
// del alumno. Streamlit lo muestra tal cual; acá se deja pasar solo el formato
// básico, para que un texto manipulado no pueda meter scripts en la página.
const ETIQUETAS_PERMITIDAS = new Set(["P", "B", "STRONG", "U", "I", "EM", "BR", "HR", "UL", "OL", "LI"]);
function evaluacionLegible(texto) {
  // Las evaluaciones enviadas desde el sistema son HTML; las reconstruidas
  // desde el buzón quedaron como texto plano, y en HTML se les juntaban todas
  // las líneas en un solo bloque.
  if (/<(p|br|b|strong|hr)/i.test(texto)) return htmlSeguro(texto);
  return el("div", { class: "texto-plano" }, texto);
}

function htmlSeguro(html) {
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
  const limpiar = (nodo) => {
    for (const hijo of [...nodo.childNodes]) {
      if (hijo.nodeType === Node.ELEMENT_NODE) {
        if (!ETIQUETAS_PERMITIDAS.has(hijo.tagName)) {
          hijo.replaceWith(...hijo.childNodes);
          continue;
        }
        for (const a of [...hijo.attributes]) hijo.removeAttribute(a.name);
        limpiar(hijo);
      } else if (hijo.nodeType !== Node.TEXT_NODE) {
        hijo.remove();
      }
    }
  };
  const raiz = doc.body.firstChild;
  limpiar(raiz);
  // Una etiqueta no permitida se reemplaza por sus hijos, que pueden traer
  // otras no permitidas: se repite hasta que no quede nada que limpiar.
  let antes;
  do { antes = raiz.innerHTML; limpiar(raiz); } while (raiz.innerHTML !== antes);
  return raiz;
}

// ---------------------------------------------------------------- gráficos

function temaVega() {
  const css = getComputedStyle(document.documentElement);
  const texto = css.getPropertyValue("--texto").trim();
  const tenue = css.getPropertyValue("--tenue").trim();
  const linea = css.getPropertyValue("--linea").trim();
  return {
    background: null,
    title: { color: texto, fontSize: 14, anchor: "start" },
    axis: { labelColor: tenue, titleColor: tenue, gridColor: linea, domainColor: linea, tickColor: linea },
    // Etiquetas horizontales: giradas, las categorías largas ("Muy Baja") se
    // cortaban o desaparecían por superposición.
    axisX: { labelAngle: 0, labelOverlap: "greedy" },
    legend: { labelColor: tenue, titleColor: tenue },
    view: { stroke: null },
  };
}

/**
 * Dibuja un gráfico. Si recibe `alClic`, cada barra o punto es clickeable y
 * llama a esa función con los datos de lo que se tocó.
 */
function grafico(spec, alClic = null) {
  const nodo = el("div", { class: "grafico" });
  const config = temaVega();
  if (alClic) config.mark = { cursor: "pointer" };
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

/** Serie por ítem, como `_linea` de main.py. Devuelve null si no hay nada. */
function linea(filas, y, titulo, dominio = null, alClic = null) {
  const datos = filas.filter((f) => f[y] !== null && f[y] !== undefined);
  if (!datos.length) return null;
  return grafico({
    height: ALTO, title: titulo, data: { values: datos },
    mark: { type: "line", point: true },
    encoding: {
      x: campo("Item", "ordinal", { title: "Semana", sort: filas.map((f) => f.Item) }),
      y: campo(y, "quantitative", { title: titulo, scale: dominio ? { domain: dominio } : { zero: false } }),
      tooltip: tooltips(Object.keys(filas[0])),
    },
  }, alClic);
}

function escalaOriginalidad(filasConNivel) {
  const etiquetas = filasConNivel.map((f) => f.Originalidad);
  const rango = filasConNivel.map((f) => (f.Nivel ? RAMPA[f.Nivel - 1] : SIN_NIVEL));
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
}

// ---------------------------------------------------------------- detalle

function colorOriginalidad(nivel) {
  const fondo = nivel ? RAMPA[nivel - 1] : SIN_NIVEL;
  // Los tres tonos claros llevan texto oscuro; los dos oscuros, texto blanco.
  const texto = nivel && nivel >= 4 ? "#ffffff" : "#1c1b1a";
  return `background:${fondo};color:${texto}`;
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
        ? el("div", { class: "evaluacion" }, el("p", {}, el("strong", {}, "Lo que le respondió el agente")),
          evaluacionLegible(c.EvaluacionIA))
        : null,
      el("button", {
        class: "ir-ficha", type: "button",
        onclick: () => { cerrarDetalle(); estado.pestana = "Alumnos"; estado.alumno = c.Correo; dibujar(); },
      }, "Ver su ficha completa →")));
}

function cerrarDetalle() {
  document.querySelectorAll(".cajon, .fondo-cajon").forEach((n) => n.remove());
}

/** Abre el panel lateral con las casillas que hay detrás de lo que se tocó. */
function abrirDetalle(titulo, criterio) {
  cerrarDetalle();
  const lista = llamar("_casillas", JSON.stringify(criterio));
  const personas = new Set(lista.map((c) => c.Correo)).size;
  const resumen = lista.length === personas
    ? `${lista.length} ${lista.length === 1 ? "alumno" : "alumnos"}`
    : `${lista.length} respuestas de ${personas} alumnos`;
  const fondo = el("div", { class: "fondo-cajon", onclick: cerrarDetalle });
  const cajon = el("aside", { class: "cajon", role: "dialog", "aria-label": titulo },
    el("header", {},
      el("div", {}, el("h2", {}, titulo),
        el("p", {}, `${resumen} · de la nota más baja a la más alta · despliega cada uno para ver su respuesta`)),
      el("button", { class: "cerrar", type: "button", onclick: cerrarDetalle }, "Cerrar")),
    el("div", { class: "lista" },
      lista.length ? lista.map(tarjetaCasilla) : el("p", { class: "tenue" }, "No hay casillas con ese criterio.")));
  document.body.append(fondo, cajon);
}

document.addEventListener("keydown", (e) => { if (e.key === "Escape") cerrarDetalle(); });

// ---------------------------------------------------------------- secciones

function seccionCurso() {
  const porItem = calc("por_item");
  if (!porItem.length) return [caja("info", "Todavía no hay datos para graficar.")];

  const verSemana = (d) => abrirDetalle(`Semana ${d.Item}`, { item: d.Item });
  const verSinResponder = (d) => abrirDetalle(`Semana ${d.Item} · sin responder`,
    { item: d.Item, estado: "sin_responder" });
  const g1 = linea(porItem, "NotaMedia", "Nota media por semana", [1.0, 7.0], verSemana);
  const g2 = linea(porItem, "TasaRespuesta", "Tasa de respuesta por semana (%)", [0, 100], verSinResponder);

  const dist = calc("distribucion_notas");
  const g3 = dist.length ? grafico({
    height: ALTO, title: "Distribución de notas", data: { values: dist }, mark: "bar",
    encoding: {
      x: campo("Etiqueta", "ordinal", { title: "Nota", sort: dist.map((d) => d.Etiqueta) }),
      y: campo("Alumnos", "quantitative", { title: "Evaluaciones" }),
      tooltip: tooltips(["Etiqueta", "Alumnos"]),
    },
  }, (d) => abrirDetalle(`Nota ${d.Etiqueta}`, { tramo: d.Tramo, estado: "evaluada" }))
    : el("p", { class: "tenue" }, "Sin notas para distribuir.");

  const orig = calc("distribucion_originalidad");
  const g4 = orig.length ? grafico({
    height: ALTO, title: "Originalidad según el modelo", data: { values: orig }, mark: "bar",
    encoding: {
      x: campo("Originalidad", "ordinal", { title: "", sort: orig.map((d) => d.Originalidad) }),
      y: campo("Evaluaciones", "quantitative"),
      color: campo("Originalidad", "nominal", { scale: escalaOriginalidad(orig).escala, legend: null }),
      tooltip: tooltips(["Originalidad", "Evaluaciones"]),
    },
  }, (d) => abrirDetalle(`Originalidad ${d.Originalidad}`, { originalidad: d.Originalidad }))
    : el("p", { class: "tenue" }, "Sin datos de originalidad.");

  return [
    el("div", { class: "grilla2" },
      tarjeta(g1 || el("p", { class: "tenue" }, "Sin notas todavía."), "Clic en un punto: quiénes respondieron esa semana."),
      tarjeta(g2 || el("p", { class: "tenue" }, "Sin envíos todavía."), "Clic en un punto: quiénes no respondieron esa semana.")),
    el("div", { class: "grilla2" },
      tarjeta(g3, "Clic en una barra: quiénes sacaron esa nota y qué respondieron."),
      tarjeta(g4, "Clic en una barra: las respuestas que recibieron esa categoría.")),
    desplegable("Ver la tabla por semana", tabla(porItem)),
  ];
}

function seccionOriginalidad() {
  const acumulado = calc("distribucion_originalidad");
  if (!acumulado.length) {
    return [caja("info", "Ninguna evaluación de este corte trae categoría de originalidad. "
      + "La escribe el prompt de evaluación en la línea ORIGINALIDAD:.")];
  }
  const { etiquetas, escala } = escalaOriginalidad(acumulado);
  const corr = calc("correlacion_originalidad_nota");
  const total = acumulado.reduce((s, x) => s + x.Evaluaciones, 0);

  const kpis = el("div", { class: "kpis k4" },
    kpi("Evaluaciones con categoría", total),
    kpi("Nivel medio", corr.NivelMedio, "", "Promedio en la escala 1 (Muy Baja) a 5 (Muy Alta)."),
    kpi("Nota media de esas casillas", corr.NotaMedia),
    kpi("Correlación con la nota", corr.R, "",
      "Entre −1 y 1. Cerca de 0, la originalidad y la nota se mueven por separado; "
      + "cerca de 1, el modelo le pone mejor nota a quien le ve más originalidad. Es una "
      + "correlación de rangos: sirve para la dirección y la fuerza, no para leerla como regresión."));

  const porItem = calc("originalidad_por_item");
  const vistos = new Set();
  const nivelMedio = porItem.filter((f) => {
    if (f.NivelMedio === null || vistos.has(f.Item)) return false;
    vistos.add(f.Item);
    return true;
  }).map((f) => ({ Item: f.Item, NivelMedio: f.NivelMedio }));

  const gLinea = nivelMedio.length >= 2 ? grafico({
    height: ALTO, title: "Nivel medio de originalidad por semana", data: { values: nivelMedio },
    mark: { type: "line", point: true, strokeWidth: 2, color: RAMPA[4] },
    encoding: {
      x: campo("Item", "ordinal", { title: "Semana", sort: nivelMedio.map((f) => f.Item) }),
      y: campo("NivelMedio", "quantitative", { title: "Nivel (1 a 5)", scale: { domain: [1, 5] } }),
      tooltip: tooltips(["Item", "NivelMedio"]),
    },
  }, (d) => abrirDetalle(`Semana ${d.Item}`, { item: d.Item, estado: "evaluada" }))
    : el("p", { class: "tenue" }, "Hace falta más de una semana para ver la evolución.");

  const itemsOrden = [...new Set(porItem.map((f) => f.Item))];
  const gComposicion = porItem.length ? grafico({
    height: ALTO, title: "Composición por semana (%)", data: { values: porItem },
    mark: { type: "bar", stroke: "white", strokeWidth: 2 },
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
    height: 240, title: "Nota media según la originalidad que se le vio", data: { values: vsNota },
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
      tarjeta(gLinea, "Clic en un punto: las respuestas evaluadas de esa semana."),
      tarjeta(gComposicion, "Clic en un tramo: las respuestas de esa categoría esa semana.")),
    tarjeta(gVsNota, "Clic en una barra: las respuestas de esa categoría, con su nota."),
    gVsNota && el("p", { class: "nota-pie" },
      "Cada barra es el promedio de las notas que sacaron las respuestas de esa categoría. "
      + "La cantidad de evaluaciones detrás de cada una está en la tabla; una categoría con "
      + "tres casos no dice lo mismo que una con cien."),
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
      caja("info", "Este semestre no tiene dos grupos comparables. La división "
        + "Control / Tratamiento se activa con GRUPO_CONTROL_TRATAMIENTO."),
      pg.length ? tabla(pg) : null,
    ];
  }

  const itemsOrden = [...new Set(pg.map((f) => f.Item))];
  const porGrupo = (y, titulo, dominio) => {
    const sub = pg.filter((f) => f[y] !== null && f[y] !== undefined);
    if (!sub.length) return el("p", { class: "tenue" }, "Sin datos.");
    return grafico({
      height: ALTO, title: titulo, data: { values: sub }, mark: { type: "line", point: true },
      encoding: {
        x: campo("Item", "ordinal", { title: "Semana", sort: itemsOrden }),
        y: campo(y, "quantitative", { title: titulo, scale: { domain: dominio } }),
        color: campo("Grupo", "nominal", { title: "Grupo" }),
        tooltip: tooltips(["Item", "Grupo", "NotaMedia", "TasaRespuesta", "Evaluados"]),
      },
    }, (d) => abrirDetalle(`Semana ${d.Item} · ${d.Grupo}`, { item: d.Item, grupo: d.Grupo }));
  };

  // La diferencia entre brazos es el número que interesa del estudio. Es solo
  // un reacomodo de las filas de por_grupo para el gráfico, como el pivot de main.py.
  const pivote = itemsOrden.map((item) => {
    const c = pg.find((f) => f.Item === item && f.Grupo === "control");
    const t = pg.find((f) => f.Item === item && f.Grupo === "tratamiento");
    const control = c ? c.NotaMedia : null;
    const tratamiento = t ? t.NotaMedia : null;
    const Diferencia = control !== null && tratamiento !== null
      ? Math.round((tratamiento - control) * 100) / 100 : null;
    return { Item: item, control, tratamiento, Diferencia };
  }).filter((f) => f.Diferencia !== null);

  const gDif = distintos.has("control") && distintos.has("tratamiento") && pivote.length ? grafico({
    height: 200, title: "Diferencia de nota (Tratamiento − Control)", data: { values: pivote },
    mark: "bar",
    encoding: {
      x: campo("Item", "ordinal", { title: "Semana", sort: itemsOrden }),
      y: campo("Diferencia", "quantitative", { title: "Puntos de nota" }),
      color: { condition: { test: "datum.Diferencia > 0", value: "#2e7d32" }, value: "#c62828" },
      tooltip: tooltips(["Item", "control", "tratamiento", "Diferencia"]),
    },
  }, (d) => abrirDetalle(`Semana ${d.Item} · los dos grupos`, { item: d.Item, estado: "evaluada" })) : null;

  return [
    el("p", { class: "nota-pie" }, "Control y Tratamiento reciben preguntas distintas sobre el mismo "
      + "tema. El grupo de cada alumno se fija una sola vez y no cambia."),
    el("div", { class: "grilla2" },
      tarjeta(porGrupo("NotaMedia", "Nota media por grupo", [1.0, 7.0]),
        "Clic en un punto: los alumnos de ese grupo esa semana."),
      tarjeta(porGrupo("TasaRespuesta", "Tasa de respuesta por grupo (%)", [0, 100]),
        "Clic en un punto: los alumnos de ese grupo esa semana.")),
    tarjeta(gDif, "Clic en una barra: las notas de esa semana en los dos grupos."),
    desplegable("Ver la tabla por grupo", tabla(pg)),
  ];
}

function seccionAlumnos() {
  const pa = calc("por_alumno");
  if (!pa.length) return [caja("info", "Sin alumnos que mostrar con estos filtros.")];

  if (!estado.alumno || !pa.some((a) => a.Correo === estado.alumno)) estado.alumno = pa[0].Correo;

  const selector = el("select", {
    onchange: (e) => { estado.alumno = e.target.value; dibujarPestana(); },
  }, pa.map((a) => el("option", { value: a.Correo, selected: a.Correo === estado.alumno },
    `${a.Nombre}  ·  ${a.Correo}`)));

  const f = llamar("_ficha", estado.alumno);
  const partes = [
    el("p", { class: "nota-pie" }, "Ordenado de la nota media más baja a la más alta."),
    tabla(pa, ["Nombre", "Grupo", "NotaMedia", "TasaRespuesta", "Respondieron",
      "Evaluados", "SinResponder", "NotaMin", "NotaMax", "Correo"]),
    el("hr"),
    el("h4", {}, "Ficha individual"),
    el("label", {}, el("span", { class: "tenue" }, "Alumno "), selector),
  ];
  if (!f || !f.Resumen) return partes;

  const r = f.Resumen;
  partes.push(el("div", { class: "kpis k5" },
    kpi("Nota media", r.NotaMedia),
    kpi("Respondió", `${r.Respondieron}/${r.Enviados}`),
    kpi("Evaluadas", r.Evaluados),
    kpi("Sin responder", r.SinResponder),
    kpi("Grupo", f.Grupo || "—")));

  const serie = f.Casillas.filter((c) => c.Nota !== null && c.Nota !== undefined);
  if (serie.length >= 2) {
    partes.push(grafico({
      height: 220, title: `Notas de ${f.Nombre}`, data: { values: serie },
      mark: { type: "line", point: true },
      encoding: {
        x: campo("Item", "ordinal", { title: "Semana", sort: f.Casillas.map((c) => c.Item) }),
        y: campo("Nota", "quantitative", { scale: { domain: [1.0, 7.0] } }),
        tooltip: tooltips(["Item", "Nota", "Originalidad"]),
      },
    }));
  }

  for (const c of f.Casillas) {
    const est = c.NotaTexto ? `nota ${c.NotaTexto}` : c.Respondio ? "respondió, sin evaluar" : "sin responder";
    partes.push(desplegable(`Semana ${c.Item} — ${est}`,
      c.Respuesta
        ? [el("p", {}, el("strong", {}, "Lo que respondió")), el("div", { class: "respuesta" }, c.Respuesta)]
        : el("p", { class: "tenue" }, "No hay texto de respuesta guardado."),
      c.EvaluacionIA
        ? [el("p", {}, el("strong", {}, "Lo que le respondió el agente")), evaluacionLegible(c.EvaluacionIA)]
        : null,
      c.Modelo ? el("p", { class: "tenue" }, `Modelo: ${c.Modelo}`) : null,
      c.Respondio || c.NotaTexto ? formularioAjuste(c) : null));
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
  const motivo = el("input", { type: "text", size: 40, placeholder: "por qué se ajusta", "aria-label": "Motivo" });
  const destino = el("div");
  const boton = el("button", { class: "descarga", type: "button" }, "Guardar ajuste");
  boton.addEventListener("click", async () => {
    const n = nota.value.trim().replace(".", ",");
    if (!/^\d{1,2}(,\d)?$/.test(n) || Number(n.replace(",", ".")) > 7) {
      destino.replaceChildren(caja("aviso", "La nota se escribe como 6,5 (entre 1,0 y 7,0)."));
      return;
    }
    if (motivo.value.trim().length < 5) {
      destino.replaceChildren(caja("aviso", "Escribe el motivo: queda registrado junto al ajuste."));
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
              "Recargar la reportería para ver la nota nueva"));
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
      el("p", { class: "nota-pie" }, "Para cuando el modelo se equivocó. Queda registrado quién la cambió, cuándo, la "
        + "nota anterior y el motivo. El alumno no recibe ningún correo."),
      el("div", { class: "fila-campos" }, el("label", { class: "campo" }, "Nota nueva", nota),
        el("label", { class: "campo" }, "Motivo", motivo), boton),
      destino));
}

function seccionPendientes() {
  // Las listas salen de casillas(), con el mismo criterio que usan los conteos
  // sin_responder() y pendientes_de_evaluar(); la prueba web.py vigila que
  // coincidan. Así se pueden desplegar y leer ahí mismo.
  const sinResp = llamar("_casillas", JSON.stringify({ estado: "sin_responder" }));
  const pend = llamar("_casillas", JSON.stringify({ estado: "sin_nota" }));
  return [
    el("h4", {}, `Sin responder — ${sinResp.length}`),
    sinResp.length ? sinResp.map(tarjetaCasilla) : caja("exito", "Todos respondieron lo que se les envió."),
    el("hr"),
    el("h4", {}, `Respondieron pero no tienen nota — ${pend.length}`),
    pend.length ? [
      el("p", { class: "nota-pie" }, "Puede ser que respondieran después de la fecha de revisión, "
        + "en cuyo caso no corresponde evaluarlos. Despliega cada uno para leer su respuesta."),
      pend.map(tarjetaCasilla),
    ] : caja("exito", "No hay respuestas pendientes de evaluación."),
  ];
}

const SECCIONES = {
  Curso: seccionCurso, Originalidad: seccionOriginalidad, Grupos: seccionGrupos,
  Alumnos: seccionAlumnos, Pendientes: seccionPendientes,
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

function chips(opciones, seleccion) {
  return el("div", { class: "chips" }, opciones.map((o) => el("button", {
    class: "chip", type: "button", "aria-pressed": String(seleccion.has(o)),
    onclick: () => {
      if (seleccion.has(o)) seleccion.delete(o); else seleccion.add(o);
      dibujar();
    },
  }, o)));
}

let contenedorPestana = null;

function dibujarPestana() {
  if (!contenedorPestana) return;
  contenedorPestana.replaceChildren(...SECCIONES[estado.pestana]().flat().filter(Boolean));
}

function haceCuanto(iso) {
  if (!iso) return null;
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 1) return "recién";
  if (min < 60) return `hace ${min} min`;
  const h = Math.round(min / 60);
  if (h < 48) return `hace ${h} h`;
  return `hace ${Math.round(h / 24)} días`;
}

function dibujar() {
  const sem = estado.semestres.find((x) => x.id === estado.semestre);
  const cuando = sem ? haceCuanto(sem.actualizado) : null;
  const subtitulo = el("p", { class: "subtitulo" },
    cuando ? `Datos subidos ${cuando} desde el equipo que opera el curso.` : "");
  const cabecera = el("div", { class: "cabecera" },
    el("div", {},
      el("label", { for: "semestre" }, "Semestre"),
      el("select", {
        id: "semestre",
        title: "Solo cambia lo que se ve acá. El semestre sobre el que operan los envíos se cambia en el equipo que opera el curso.",
        onchange: async (e) => { await cargarSemestre(e.target.value); dibujar(); },
      }, estado.semestres.map((s) => el("option", { value: s.id, selected: s.id === estado.semestre }, s.id)))),
    estado.activo && estado.semestre !== estado.activo
      ? caja("aviso", `Estás viendo ${estado.semestre}, pero el semestre activo —sobre el que corren los envíos— es ${estado.activo}.`)
      : null);

  // Una selección vacía no filtra, igual que el multiselect de Streamlit: la
  // función filtrar() de Python trata la lista vacía como "sin filtro".
  const n = llamar("_filtrar", JSON.stringify([...estado.selItems]), JSON.stringify([...estado.selGrupos]));

  const filtros = el("div", { class: "filtros" },
    el("div", { class: "filtro" }, el("span", {}, "Semanas"), chips(estado.items, estado.selItems)),
    el("div", { class: "filtro" }, el("span", {}, "Grupos"), chips(estado.grupos, estado.selGrupos)));

  if (!n) {
    app.replaceChildren(subtitulo, cabecera, filtros, caja("aviso", "Los filtros no dejan ninguna fila."));
    return;
  }

  const r = calc("resumen");
  const kpis = el("div", { class: "kpis" },
    kpi("Alumnos", r.Alumnos),
    kpi("Semanas", r.Items),
    kpi("Tasa de respuesta", r.TasaRespuesta, "%", "Respondieron sobre los que recibieron la pregunta.",
      `${r.Respondieron} de ${r.Enviados} enviadas`),
    kpi("Nota media", r.NotaMedia, "", null,
      r.NotaMin !== null ? `entre ${r.NotaMin} y ${r.NotaMax}` : null),
    kpi("Evaluadas", r.Evaluados, "", "Ver todas las respuestas evaluadas.",
      r.PendientesEvaluar ? `${r.PendientesEvaluar} sin nota · ver →` : "ver todas →",
      () => abrirDetalle("Respuestas evaluadas", { estado: "evaluada" })),
    kpi("Sin responder", r.SinResponder, "", "Ver a quiénes les falta responder.",
      r.SinResponder ? "ver quiénes →" : null,
      r.SinResponder ? () => abrirDetalle("Sin responder", { estado: "sin_responder" }) : null));

  const notas = [
    r.EnviosSinRegistro ? el("p", { class: "nota-pie" },
      `⚠ ${r.EnviosSinRegistro} casilla(s) sin registro de envío: se dan por enviadas porque hay `
      + "respuesta o nota. Pasa cuando el envío se hizo desde otro equipo.") : null,
    r.Modelos && r.Modelos.length ? el("p", { class: "nota-pie" }, `Modelos registrados: ${r.Modelos.join(", ")}`) : null,
  ];

  const pestanas = el("div", { class: "pestanas", role: "tablist" }, PESTANAS.map((p) => el("button", {
    class: "pestana", role: "tab", type: "button", "aria-selected": String(p === estado.pestana),
    onclick: () => { estado.pestana = p; history.replaceState(null, "", `#${p}`); dibujar(); },
  }, p)));

  contenedorPestana = el("div", { role: "tabpanel" });
  app.replaceChildren(subtitulo, cabecera, filtros, kpis, ...notas.filter(Boolean), el("hr"), pestanas,
    contenedorPestana, el("hr"),
    el("button", { class: "descarga", type: "button", onclick: descargarCsv }, "Descargar el panel en CSV"),
    sabanaDe(estado.semestre));
  dibujarPestana();
}

async function iniciar() {
  // La pestaña va en la dirección (#Grupos), para poder mandar un enlace directo.
  const pedida = decodeURIComponent(location.hash.slice(1));
  if (PESTANAS.includes(pedida)) estado.pestana = pedida;
  try {
    app.replaceChildren(el("p", { class: "cargando" }, "Cargando el motor de cálculo (la primera vez tarda unos segundos)…"));
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
    dibujar();
  } catch (e) {
    app.replaceChildren(caja("aviso", `No pude cargar la reportería: ${e.message}`));
  }
}

iniciar();
