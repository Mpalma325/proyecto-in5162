// Lo que comparten todas las páginas del sitio: armar elementos, hablar con la
// API, la barra de navegación y cómo se muestra la salida de un trabajo.

export function el(tag, attrs = {}, ...hijos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const h of hijos.flat()) {
    if (h === null || h === undefined || h === false) continue;
    n.append(h instanceof Node ? h : document.createTextNode(String(h)));
  }
  return n;
}

export function caja(tipo, texto) {
  return el("div", { class: tipo }, texto);
}

export async function api(ruta, opciones = {}) {
  const r = await fetch(ruta, { cache: "no-store", ...opciones });
  if (!r.ok) {
    const cuerpo = await r.json().catch(() => ({}));
    throw new Error(cuerpo.error || `${r.status} ${r.statusText}`);
  }
  return r.json();
}

const PAGINAS = [
  ["/", "Reportería"],
  ["/tests", "Tests Semanales"],
  ["/tareas", "Tareas"],
  ["/datos", "Datos y Configuración"],
];

/** La barra de arriba, igual en todas las páginas. */
export function navegacion() {
  // Cloudflare sirve las páginas sin ".html" (tests.html se ve en /tests).
  const aqui = location.pathname.replace(/\.html$/, "").replace(/^\/index$/, "/");
  return el("nav", { class: "navegacion" }, PAGINAS.map(([ruta, nombre]) =>
    el("a", { href: ruta, "aria-current": ruta === aqui ? "page" : null }, nombre)));
}

// Mismos colores que render_output() de Streamlit, por el primer símbolo de
// cada línea: ✓ bien, ✗ error, ⚠ aviso, ⊘ y ⋯ omitido, → acción.
const COLOR_LINEA = [["✓", "ok"], ["✗", "mal"], ["⚠", "aviso"], ["⊘", "omitido"],
  ["⋯", "omitido"], ["→", "accion"]];

/** La salida de un trabajo, con cada línea coloreada según su símbolo. */
export function salidaColoreada(texto) {
  const pre = el("pre", { class: "salida" });
  for (const linea of texto.split("\n")) {
    const inicio = linea.trimStart();
    const par = COLOR_LINEA.find(([s]) => inicio.startsWith(s));
    pre.append(el("span", { class: par ? `l-${par[1]}` : null }, linea), "\n");
  }
  return pre;
}

// ---------------------------------------------------------------- trabajos
// Pedir un trabajo al motor, mirar su salida en vivo y listar los últimos.
// Lo usan Tests Semanales y Tareas.

const ESTADOS_FINALES = new Set(["terminado", "fallido"]);

export async function pedirTrabajo(semestre, flujo, argumentos) {
  const { id } = await api("/api/trabajos", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ semestre, flujo, argumentos }),
  });
  return id;
}

/** "semana 4", "T2" o nada: lo que distingue a un trabajo de otro del mismo flujo. */
export function sobreQue(a) {
  if (a.tarea) return a.tarea;
  if (a.semana) return `semana ${a.semana}`;
  return "";
}

const sinPrefijo = (flujo) => flujo.replace(/^[a-z]+\./, "");

function vistaTrabajo(t, extra) {
  const detalle = [sinPrefijo(t.flujo), sobreQue(t.argumentos), t.prueba ? "modo prueba" : "ENVÍO REAL",
    `pedido por ${t.pedido_por}`].filter(Boolean).join(" · ");
  return [
    el("p", {}, el("span", { class: `estado ${t.estado}` }, t.estado), " ", el("span", { class: "tenue" }, detalle)),
    salidaColoreada(t.salida || "Esperando que el motor lo tome…"),
    t.estado === "terminado" ? caja("exito", "Completado sin errores") : null,
    t.estado === "fallido" ? caja("aviso", `El proceso terminó con código ${t.codigo}`) : null,
    extra ? extra(t) : null,
  ].filter(Boolean);
}

/**
 * Muestra un trabajo en `destino` y lo va actualizando hasta que termina.
 * `extra(t)` agrega algo debajo (un enlace de descarga, por ejemplo) y
 * `alTerminar(t)` se llama una vez, al final.
 */
export async function seguirTrabajo(id, destino, { extra, alTerminar } = {}) {
  clearTimeout(destino._seguimiento);
  const t = await api(`/api/trabajos/${id}`);
  destino.replaceChildren(...vistaTrabajo(t, extra));
  const pre = destino.querySelector("pre.salida");
  if (pre) pre.scrollTop = pre.scrollHeight;
  if (!ESTADOS_FINALES.has(t.estado)) {
    destino._seguimiento = setTimeout(() => seguirTrabajo(id, destino, { extra, alTerminar }), 1500);
  } else if (alTerminar) {
    alTerminar(t);
  }
  return t;
}

/**
 * La tabla "Últimos trabajos" de una página: los trabajos para los que
 * `incluye(t)` es verdadero. Clic en uno lo muestra con `alElegir(t)`.
 */
export function historialTrabajos({ incluye, columna, alElegir }) {
  const nodo = el("div");
  async function dibujar(semestre) {
    let lista = [];
    try {
      lista = (await api(`/api/trabajos?semestre=${encodeURIComponent(semestre)}`))
        .filter(incluye);
    } catch {
      return;
    }
    if (!lista.length) { nodo.replaceChildren(); return; }
    const [titulo, valor] = columna;
    nodo.replaceChildren(
      el("h4", {}, "Últimos trabajos"),
      el("p", { class: "nota-pie" }, "Siguen corriendo aunque cierres la página. Clic en uno para ver su salida."),
      el("div", { class: "tabla-envoltura" }, el("table", { class: "historial" },
        el("thead", {}, el("tr", {}, ["Cuándo", "Qué", titulo, "Modo", "Estado", "Quién"].map((c) => el("th", {}, c)))),
        el("tbody", {}, lista.map((t) => el("tr", { onclick: () => alElegir(t) },
          el("td", {}, new Date(t.creado).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" })),
          el("td", {}, sinPrefijo(t.flujo)),
          el("td", {}, valor(t.argumentos)),
          el("td", {}, t.prueba ? "prueba" : "real"),
          el("td", {}, el("span", { class: `estado ${t.estado}` }, t.estado)),
          el("td", {}, t.pedido_por)))))));
  }
  return { nodo, dibujar };
}

// ---------------------------------------------------------------- tareas

/** T1, T2... con entregas subidas o con feedback ya generado, en orden. */
export function tareasConocidas(archivos) {
  const conocidas = new Set();
  for (const { ruta } of archivos) {
    let m = ruta.match(/^tareas\/data\/entregas\/(T\d{1,2})\//);
    if (m) conocidas.add(m[1]);
    m = ruta.match(/^tareas\/data\/salidas\/feedback_(T\d{1,2})\.csv$/);
    if (m) conocidas.add(m[1]);
  }
  return [...conocidas].sort((a, b) => Number(a.slice(1)) - Number(b.slice(1)));
}

// ---------------------------------------------------------------- elegir qué procesar

function cuando(texto) {
  const d = new Date(String(texto || "").replace(" ", "T"));
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString("es-CL", { dateStyle: "short", timeStyle: "medium" });
}

/**
 * Después de una corrida en modo prueba de evaluar o corregir: las respuestas
 * que se procesarían, con casillas, y un botón para procesar solo esas.
 * `ruta` es el JSON que dejó el script (…/cache/candidatos_<item>.json) y
 * `alProcesar(correos)` pide el trabajo real con esa lista.
 */
export function elegirCandidatos({ semestre, ruta, verbo, alProcesar }) {
  const nodo = el("div", { class: "candidatos" }, el("p", { class: "cargando" }, "Cargando las respuestas…"));
  const url = `/api/archivo/${encodeURIComponent(semestre)}/${ruta.split("/").map(encodeURIComponent).join("/")}`;
  fetch(url, { cache: "no-store" }).then((r) => (r.ok ? r.json() : [])).then((lista) => {
    if (!lista.length) {
      nodo.replaceChildren(caja("info", "No hay respuestas pendientes para elegir."));
      return;
    }
    const casillas = lista.map((c) => el("input", { type: "checkbox", checked: !c.ya_tiene_nota, value: c.correo }));
    const boton = el("button", { class: "primario peligro", type: "button" });
    const actualizar = () => {
      const n = casillas.filter((x) => x.checked).length;
      boton.textContent = `${verbo} ${n === 1 ? "la elegida" : `las ${n} elegidas`} (envío real)`;
      boton.disabled = n === 0;
    };
    casillas.forEach((x) => x.addEventListener("change", actualizar));
    const todas = (v) => { casillas.forEach((x) => { x.checked = v; }); actualizar(); };
    boton.addEventListener("click", () => {
      const elegidos = casillas.filter((x) => x.checked).map((x) => x.value);
      const nombres = lista.filter((c) => elegidos.includes(c.correo)).map((c) => c.nombre).join(", ");
      if (!confirm(`Vas a ${verbo.toLowerCase()} y mandarle el feedback por correo a: ${nombres}.\n\n`
        + "Las demás quedan como están. ¿Confirmas?")) return;
      boton.disabled = true;
      alProcesar(elegidos);
    });
    actualizar();
    nodo.replaceChildren(
      el("h4", {}, "Elegir qué respuestas procesar"),
      el("p", { class: "nota-pie" }, "Las no marcadas quedan como están: sin nota y, en los tests, sin leer en el "
        + "buzón, así que se pueden procesar otro día."),
      el("div", { class: "acciones" },
        el("button", { class: "enlace", type: "button", onclick: () => todas(true) }, "Todas"),
        el("button", { class: "enlace", type: "button", onclick: () => todas(false) }, "Ninguna")),
      ...lista.map((c, i) => el("details", { class: "candidato" },
        el("summary", {}, el("label", { class: "interruptor", onclick: (e) => e.stopPropagation() }, casillas[i],
          el("strong", {}, c.nombre)),
          el("span", { class: "tenue" }, [cuando(c.llegada), c.grupo, c.pregunta].filter(Boolean).join(" · ")),
          c.ya_tiene_nota ? el("span", { class: "estado fallido" }, `ya tiene nota ${c.ya_tiene_nota}`) : null),
        el("div", { class: "contenido respuesta" }, c.respuesta))),
      el("div", { class: "acciones" }, boton));
  }).catch((e) => nodo.replaceChildren(caja("aviso", `No pude leer la lista: ${e.message}`)));
  return nodo;
}
