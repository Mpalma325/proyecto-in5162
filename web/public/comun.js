// Lo que comparten todas las páginas del sitio: armar elementos, hablar con la
// API, la barra de navegación y cómo se muestra la salida de un trabajo.

import { formatoUsd, leerConsumo, leerPrecios, sumarConsumo, textoConsumo } from "./consumo.js";

export function el(tag, attrs = {}, ...hijos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  // Aplanado completo: con un solo nivel, una lista dentro de otra (como las
  // semanas de la ficha de un alumno) se mostraba como "[object HTMLDivElement]".
  for (const h of hijos.flat(Infinity)) {
    if (h === null || h === undefined || h === false) continue;
    n.append(h instanceof Node ? h : document.createTextNode(String(h)));
  }
  return n;
}

export function caja(tipo, texto) {
  return el("div", { class: tipo }, texto);
}

export async function api(ruta, opciones = {}) {
  let r;
  try {
    r = await fetch(ruta, { cache: "no-store", ...opciones });
  } catch {
    throw new Error("No hay conexión con el sitio. Revisa tu internet y vuelve a intentarlo.");
  }
  if (!r.ok) {
    const cuerpo = await r.json().catch(() => ({}));
    throw new Error(mensajeDeError(r.status, cuerpo.error));
  }
  return r.json();
}

/**
 * Un error de la API dicho para quien usa el sitio. Los 4xx del Worker ya
 * vienen explicados ("El archivo cambió en la nube…"); lo demás se traduce.
 */
export function mensajeDeError(estado, delSitio) {
  if (estado === 401 || estado === 403) {
    return "Tu sesión no tiene acceso o venció. Recarga la página para volver a entrar.";
  }
  if (estado >= 500) {
    return `El sitio tuvo un problema y no pudo responder (${estado}). Espera un momento y vuelve a intentarlo.`;
  }
  return delSitio || `No se pudo completar (${estado}).`;
}

/** El semestre sobre el que trabaja la página, con un enlace a donde se cambia. */
export function chipSemestre(semestre) {
  return el("a", { class: "chip-semestre", href: "/datos#datos", title: "El semestre activo se cambia en Configuración" },
    "Semestre ", el("strong", {}, semestre || "sin elegir"));
}

// El código del curso (CURSO en wrangler.toml) en el título de la pestaña y en
// el encabezado. Las páginas traen "IN5162" escrito; otro curso solo cambia la
// variable. Fuera del navegador (las pruebas) no hay a quién preguntarle.
if (typeof location !== "undefined" && typeof document !== "undefined" && document.querySelectorAll) {
  api("/api/curso").then(({ curso }) => {
    if (!curso || curso === "IN5162") return;
    document.title = document.title.replace("IN5162", curso);
    document.querySelectorAll("h1").forEach((h) => { h.textContent = h.textContent.replace("IN5162", curso); });
  }).catch(() => {});
}

const PAGINAS = [
  ["/", "Inicio"],
  ["/tests", "Tests semanales"],
  ["/tareas", "Tareas"],
  ["/resultados", "Resultados"],
  ["/datos", "Configuración"],
];

/** La barra de arriba, igual en todas las páginas. */
export function navegacion() {
  // Cloudflare sirve las páginas sin ".html" (tests.html se ve en /tests).
  const aqui = location.pathname.replace(/\.html$/, "").replace(/^\/index$/, "/");
  const nav = el("nav", { class: "navegacion" }, PAGINAS.map(([ruta, nombre]) =>
    el("a", { href: ruta, "aria-current": ruta === aqui ? "page" : null }, nombre)));
  centrarSeleccion(nav);
  return nav;
}

/**
 * Las pestañas de una página, agrupadas, con un rótulo chico sobre cada grupo.
 * Por defecto tienen forma de pestaña de carpeta. Con `flujo`, los pasos de un
 * ciclo (los grupos con `flechas`) van como una barra de progreso de flechas
 * encadenadas: hecho, el que toca, el que se está viendo y los que faltan se
 * distinguen por el color. Cada paso lleva su número (✓ si está hecho) y,
 * debajo, en qué va.
 *
 *   grupos: [{ rotulo, flechas?, pestanas: [{ id, titulo, numero?, detalle?, hecho?, toca? }] }]
 */
export function barraPestanas({ grupos, actual, alElegir, etiqueta, flujo = false }) {
  const barra = el("div", { class: flujo ? "pestanas flujo" : "pestanas", role: "tablist", "aria-label": etiqueta },
    grupos.map((g) => el("div", { class: "grupo-pestanas" },
      g.rotulo ? el("span", { class: "rotulo-grupo" }, g.rotulo) : null,
      el("div", { class: g.flechas ? "fila-pestanas flechas" : "fila-pestanas" }, g.pestanas.map((p) => el("button", {
        class: ["pestana", p.numero ? "paso" : "", p.hecho ? "hecha" : "", p.toca ? "toca" : ""].filter(Boolean).join(" "),
        role: "tab", type: "button", "aria-selected": String(p.id === actual), onclick: () => alElegir(p.id),
      },
      p.numero ? el("span", { class: "num" }, p.hecho ? "✓" : String(p.numero)) : null,
      el("span", { class: "titulo-pestana" }, p.titulo),
      p.detalle ? el("span", { class: "detalle-pestana" }, p.detalle) : null))))));
  centrarSeleccion(barra);
  return barra;
}

const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const dos = (n) => String(n).padStart(2, "0");

/** "lun 19/10, 10:15" (sin la hora si es fin del día). */
export function fechaCorta(fecha) {
  if (!fecha) return "";
  const dia = `${DIAS[fecha.getDay()]} ${dos(fecha.getDate())}/${dos(fecha.getMonth() + 1)}`;
  const finDelDia = fecha.getHours() === 23 && fecha.getMinutes() === 59;
  return finDelDia ? dia : `${dia}, ${fecha.getHours()}:${dos(fecha.getMinutes())}`;
}

/** "en 2 días", "en 5 h", "hace 3 días": lo que falta o lo que pasó desde `fecha`. */
export function enCuanto(fecha, ahora = new Date()) {
  const ms = fecha - ahora;
  const h = Math.round(Math.abs(ms) / 36e5);
  const texto = h < 1 ? "menos de una hora" : h < 36 ? `${h} h` : `${Math.round(h / 24)} días`;
  return ms >= 0 ? `en ${texto}` : `hace ${texto}`;
}

/**
 * En una barra que se desliza de lado (en celular no cabe entera), deja a la
 * vista la opción marcada. Solo mueve la barra, nunca la página.
 */
export function centrarSeleccion(barra,
  selector = '[aria-selected="true"], [aria-current="page"], [aria-current="true"]') {
  requestAnimationFrame(() => {
    const marcado = barra.querySelector(selector);
    if (!marcado || barra.scrollWidth <= barra.clientWidth) return;
    const [b, m] = [barra.getBoundingClientRect(), marcado.getBoundingClientRect()];
    barra.scrollLeft += m.left - b.left - (barra.clientWidth - m.width) / 2;
  });
}

// Mismos colores que render_output() de Streamlit, por el primer símbolo de
// cada línea: ✓ bien, ✗ error, ⚠ aviso, ⊘ y ⋯ omitido, → acción.
const COLOR_LINEA = [["✓", "ok"], ["✗", "mal"], ["⚠", "aviso"], ["⊘", "omitido"],
  ["⋯", "omitido"], ["→", "accion"]];

/** La salida de un trabajo, con cada línea coloreada según su símbolo. */
export function salidaColoreada(texto, clase = "salida") {
  const pre = el("pre", { class: clase });
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

const ESTADOS_FINALES = new Set(["terminado", "fallido", "cancelado"]);

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

// Cómo se llama cada flujo en pantalla: el nombre de su pestaña. El id no cambia.
const NOMBRE_FLUJO = {
  "tests.enviar": "Enviar preguntas", "tests.evaluar": "Evaluar respuestas", "tests.resumen": "Resumen semana",
  "tests.tutoria": "Responder dudas", "tests.experimento": "Probar criterio",
  "tareas.chequeo": "Revisar entregas", "tareas.generar": "Generar preguntas", "tareas.enviar": "Enviar preguntas",
  "tareas.recolectar": "Recolectar respuestas", "tareas.corregir": "Corregir", "tareas.segunda": "Segunda oportunidad",
  "datos.ajustar": "Ajustar nota", "datos.sabana": "Armar la sábana", "datos.panel": "Actualizar los resultados",
};

function nombreFlujo(t) {
  const nombre = NOMBRE_FLUJO[t.flujo] || sinPrefijo(t.flujo);
  const paso = t.flujo === "tareas.segunda" && t.argumentos?.paso;
  return paso ? `${nombre} (${paso})` : nombre;
}

// Los flujos cuyo modo prueba es una simulación: no mandan correos ni guardan
// notas. Los demás (resumen, generar, recolectar, preparar...) quedan con
// prueba = 1 porque nadie lo pide en falso, pero sí llaman al modelo o
// escriben archivos: de ellos no se puede decir "no se hizo nada".
const SIMULABLES = new Set(["tests.enviar", "tests.evaluar", "tests.tutoria", "tests.experimento",
  "tareas.enviar", "tareas.corregir"]);
const simula = (t) => (t.flujo === "tareas.segunda" ? t.argumentos?.paso === "enviar" : SIMULABLES.has(t.flujo));

/** Si el trabajo fue una simulación: no mandó correos ni guardó notas. */
export const esSimulacion = (t) => Boolean(t.prueba) && simula(t);

// Un trabajo y su repetición: mismo flujo, misma semana o tarea, mismo paso.
const claveTrabajo = (t) => [t.flujo, t.argumentos?.semana ?? "", t.argumentos?.tarea ?? "", t.argumentos?.paso ?? ""]
  .join("|");

/**
 * Trabajos reales que fallaron y no se volvieron a correr bien. Una simulación
 * fallida no hizo nada, y un fallo que después se repitió con éxito ya está
 * resuelto: ninguno de los dos se marca.
 */
export function fallidosSinResolver(trabajos) {
  return trabajos.filter((t) => t.estado === "fallido" && !esSimulacion(t)
    && !trabajos.some((o) => o.estado === "terminado" && !esSimulacion(o) && claveTrabajo(o) === claveTrabajo(t)
      && new Date(o.creado) > new Date(t.creado)));
}

/** Si el trabajo, corrido de verdad, manda correos a los alumnos. */
function mandaCorreos(t) {
  if (t.prueba || !simula(t) || t.flujo === "tests.experimento") return false;
  return !(t.flujo === "tareas.corregir" && t.argumentos?.no_enviar);
}

/** "real" en rojo, "simulación" neutra; lo que no manda correos, apagado. Solo dice; no decide nada. */
function insigniaModo(t) {
  if (t.prueba && simula(t)) {
    return el("span", { class: "estado modo simulacion", title: "No mandó correos ni guardó notas" }, "simulación");
  }
  if (!t.prueba && t.flujo !== "tests.experimento") {
    return el("span", { class: "estado modo real", title: mandaCorreos(t) ? "Manda correos reales" : "Guarda notas reales" },
      "real");
  }
  return el("span", { class: "estado modo sin-correos", title: "No manda correos" }, "sin correos");
}

/**
 * Las primeras líneas que escribe el motor ("$ python …", "(bajados …)") y el
 * resto. Solo se separan para mostrarlas: el texto del trabajo no se toca.
 */
function separarTecnico(texto) {
  const lineas = texto.split("\n");
  let fin = 0;
  for (let i = 0; i < lineas.length; i++) {
    if (/^\$ |^\(.*\)\s*$/.test(lineas[i])) fin = i + 1;
    else if (lineas[i].trim()) break;
  }
  return [lineas.slice(0, fin).join("\n").trimEnd(), lineas.slice(fin).join("\n").replace(/^\s*\n/, "")];
}

// Cuántas líneas de cada símbolo: lo primero que hay que leer de una salida.
const CONTEO_SALIDA = [
  ["✓", "ok", (n) => `${n} hecha${n === 1 ? "" : "s"}`],
  ["→", "accion", (n, simulacion) => (simulacion ? `${n} se haría${n === 1 ? "" : "n"}`
    : `${n} acci${n === 1 ? "ón" : "ones"}`)],
  ["⊘", "omitido", (n) => `${n} omitida${n === 1 ? "" : "s"}`],
  ["⚠", "aviso", (n) => `${n} advertencia${n === 1 ? "" : "s"}`],
  ["✗", "mal", (n) => `${n} error${n === 1 ? "" : "es"}`],
];

function contarLineas(texto) {
  const cuenta = {};
  for (const linea of texto.split("\n")) {
    const inicio = linea.trimStart();
    const par = CONTEO_SALIDA.find(([s]) => inicio.startsWith(s));
    if (par) cuenta[par[0]] = (cuenta[par[0]] || 0) + 1;
  }
  return cuenta;
}

/** Cómo terminó y qué hacer ahora. */
function cierreTrabajo(t, cuenta, simulacion) {
  if (t.estado === "terminado") {
    const [avisos, errores] = [cuenta["⚠"] || 0, cuenta["✗"] || 0];
    if (!avisos && !errores) {
      return caja("exito", simulacion ? "Simulación terminada sin errores: no se mandó ni guardó nada."
        : "Terminó sin errores.");
    }
    const partes = [errores && `${errores} error${errores === 1 ? "" : "es"}`,
      avisos && `${avisos} advertencia${avisos === 1 ? "" : "s"}`].filter(Boolean).join(" y ");
    return caja("aviso", `Terminó con ${partes}: revisa en la salida las líneas marcadas con ${
      [errores && "✗", avisos && "⚠"].filter(Boolean).join(" o ")}.`);
  }
  if (t.estado === "cancelado") {
    return caja("info", simulacion ? "Se detuvo antes de terminar. Era una simulación: no se mandó ni guardó nada."
      : "Se detuvo antes de terminar. Lo que alcanzó a hacer quedó guardado; si lo vuelves a ejecutar, sigue con lo que faltó.");
  }
  if (t.estado === "fallido") {
    let que;
    if (t.prueba && simula(t)) que = "No se mandó ni guardó nada; puedes volver a ejecutarlo.";
    else if (mandaCorreos(t)) que = "Puede que algunos correos ya hayan salido: revisa la salida antes de reintentar.";
    else que = "No salió ningún correo, pero puede que haya guardado parte del resultado: revisa la salida antes de "
      + "volver a ejecutarlo.";
    return caja("aviso", el("span", {}, el("strong", {}, "El trabajo falló. "), que,
      el("span", { class: "tenue" }, ` (código ${t.codigo ?? "?"})`)));
  }
  return null;
}

// Los precios de la API, una sola vez por página (Configuración › Parámetros).
let preciosPedidos = null;
export function preciosApi() {
  preciosPedidos ??= api("/api/parametros")
    .then((ps) => leerPrecios(ps.find((p) => p.clave === "PRECIOS_API")?.valor))
    .catch(() => ({}));
  return preciosPedidos;
}

// El avance que imprimen los flujos (modulos/progreso.py): "@@progreso 3/24 respuestas".
const LINEA_PROGRESO = /^@@progreso (\d+)\/(\d+)(?: (.*))?$/gm;

/** El último avance de una salida, o null si el flujo no lo informa. */
export function progresoDe(salida) {
  const todas = [...String(salida || "").matchAll(LINEA_PROGRESO)];
  if (!todas.length) return null;
  const [, hechos, total, unidad] = todas[todas.length - 1];
  return { hechos: Number(hechos), total: Number(total), unidad: unidad || "" };
}

/** La salida sin las líneas de avance, que no son para leer: la línea entera, con su salto. */
export const sinProgreso = (salida) => String(salida || "").replace(/^@@progreso [^\n]*(?:\n|$)/gm, "");

/** La barra mientras corre: cuántos van de cuántos. */
function barraProgreso(t) {
  const p = t.estado === "corriendo" || t.estado === "cancelando" ? progresoDe(t.salida) : null;
  if (!p) return null;
  const pct = Math.min(100, Math.round((p.hechos / p.total) * 100));
  return el("div", {
    class: "progreso-trabajo", role: "progressbar",
    "aria-valuemin": "0", "aria-valuemax": String(p.total), "aria-valuenow": String(p.hechos),
  },
    el("div", { class: "barra-progreso" }, el("span", { style: `width: ${pct}%` })),
    el("span", { class: "texto-progreso" }, `${p.hechos} de ${p.total}${p.unidad ? ` ${p.unidad}` : ""}`));
}

function vistaTrabajo(t, extra, precios = {}) {
  const simulacion = Boolean(t.prueba) && simula(t);
  const [tecnico, resto] = separarTecnico(sinProgreso(t.salida));
  const cuenta = contarLineas(resto);
  const conteo = CONTEO_SALIDA.filter(([s]) => cuenta[s])
    .flatMap(([s, clase, texto], i) => [i ? " · " : "", el("span", { class: `l-${clase}` }, `${s} ${texto(cuenta[s], simulacion)}`)]);
  const detalle = [nombreFlujo(t), sobreQue(t.argumentos || {}), `pedido por ${t.pedido_por}`]
    .filter(Boolean).join(" · ");
  const esperando = t.estado === "pendiente" ? "Esperando que el motor lo tome…"
    : t.estado === "cancelando" ? "Deteniéndose…"
      : ESTADOS_FINALES.has(t.estado) ? "(el trabajo no dejó salida)" : "Corriendo…";
  return [
    el("p", { class: "cabeza-trabajo" }, el("span", { class: `estado ${t.estado}` }, t.estado), " ", insigniaModo(t), " ",
      el("span", { class: "tenue" }, detalle), botonDetener(t)),
    simulacion && t.estado !== "fallido"
      ? el("p", { class: "titulo-salida" }, "Esto es lo que pasaría (no se hizo nada)") : null,
    barraProgreso(t),
    conteo.length ? el("p", { class: "resumen-salida" }, "En la salida: ", conteo) : null,
    consumoDe(t, precios),
    tecnico ? el("details", { class: "detalle-tecnico" }, el("summary", {}, "Detalle técnico"),
      salidaColoreada(tecnico, "salida tecnica")) : null,
    salidaColoreada(resto.trim() ? resto : esperando),
    cierreTrabajo(t, cuenta, simulacion),
    extra ? extra(t) : null,
  ].filter(Boolean);
}

/**
 * Detener un trabajo que no ha terminado. El motor lo para entre un alumno y
 * otro, nunca a la mitad de un correo; lo hecho hasta ahí queda guardado.
 */
function botonDetener(t) {
  if (t.estado !== "pendiente" && t.estado !== "corriendo") return null;
  return el("button", {
    class: "enlace detener", type: "button",
    onclick: async (e) => {
      if (!confirm("¿Detener este trabajo? Para antes del alumno siguiente; lo que ya hizo queda guardado.")) return;
      e.target.disabled = true;
      try {
        await api(`/api/trabajos/${t.id}/cancelar`, { method: "POST" });
      } catch (err) {
        alert(`No pude detenerlo: ${err.message}`);
        e.target.disabled = false;
      }
    },
  }, "Detener");
}

/** Lo que gastó el trabajo en la API, si llamó al modelo. */
function consumoDe(t, precios) {
  const usos = leerConsumo(t.salida);
  return usos.length ? el("p", { class: "consumo-trabajo" }, "Uso de API: ", textoConsumo(sumarConsumo(usos, precios)))
    : null;
}

/**
 * Muestra un trabajo en `destino` y lo va actualizando hasta que termina.
 * `extra(t)` agrega algo debajo (un enlace de descarga, por ejemplo) y
 * `alTerminar(t)` se llama una vez, al final.
 */
export async function seguirTrabajo(id, destino, { extra, alTerminar } = {}) {
  clearTimeout(destino._seguimiento);
  const [t, precios] = await Promise.all([api(`/api/trabajos/${id}`), preciosApi()]);
  // Se redibuja cada 1,5 s: el detalle técnico queda como lo dejó quien mira.
  const abierto = destino.querySelector("details.detalle-tecnico")?.open;
  destino.replaceChildren(...vistaTrabajo(t, extra, precios));
  if (abierto) destino.querySelector("details.detalle-tecnico")?.setAttribute("open", "");
  const pre = destino.querySelector("pre.salida:not(.tecnica)");
  if (pre) pre.scrollTop = pre.scrollHeight;
  if (!ESTADOS_FINALES.has(t.estado)) {
    destino._seguimiento = setTimeout(() => seguirConReintentos(id, destino, { extra, alTerminar }), 1500);
  } else if (alTerminar) {
    alTerminar(t);
  }
  return t;
}

/**
 * Un sondeo que falla (se cortó la red, el sitio no respondió) se reintenta:
 * el trabajo sigue corriendo en la nube igual. Antes la vista se congelaba
 * sin avisar, y quien esperaba no sabía si el trabajo había muerto.
 */
function seguirConReintentos(id, destino, opciones, fallos = 0) {
  seguirTrabajo(id, destino, opciones).catch(() => {
    if (fallos < 8) {
      destino._seguimiento = setTimeout(() => seguirConReintentos(id, destino, opciones, fallos + 1), 3000);
      return;
    }
    destino.append(el("div", { class: "aviso" },
      "Perdí la conexión con el sitio mientras seguía este trabajo. El trabajo sigue corriendo en la nube. ",
      el("button", { class: "secundario", type: "button", onclick: () => seguirConReintentos(id, destino, opciones) },
        "Volver a revisar")));
  });
}

/**
 * La tabla "Últimos trabajos" de una página: los trabajos para los que
 * `incluye(t)` es verdadero. Clic en uno lo muestra con `alElegir(t)`.
 */
/** El costo de un trabajo en la tabla: dólares si hay precio, tokens si no, nada si no llamó al modelo. */
function costoCorto(total) {
  if (!total || !total.llamadas) return "";
  if (total.sinPrecio.length && !total.usd) return `${(total.entrada + total.salida).toLocaleString("es-CL")} tokens`;
  return formatoUsd(total.usd);
}

export function historialTrabajos({ incluye, columna, alElegir }) {
  const nodo = el("div");
  async function dibujar(semestre) {
    let lista = [];
    let costos = new Map();
    try {
      const [trabajos, consumo, precios] = await Promise.all([
        api(`/api/trabajos?semestre=${encodeURIComponent(semestre)}`),
        api(`/api/consumo/${encodeURIComponent(semestre)}`).catch(() => []),
        preciosApi()]);
      lista = trabajos.filter(incluye);
      costos = new Map(consumo.map((c) => [c.id, sumarConsumo(leerConsumo(c.lineas.join("\n")), precios)]));
    } catch {
      return;
    }
    if (!lista.length) { nodo.replaceChildren(); return; }
    const [titulo, valor] = columna;
    // La fila entera abre el trabajo, también con el teclado (Tab y Enter).
    const fila = (t) => el("tr", {
      tabindex: "0", title: "Ver la salida de este trabajo", onclick: () => alElegir(t),
      onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); alElegir(t); } },
    },
    // Fecha y hora por separado: en el celular cada una va en su línea, sin cortarse.
    el("td", {}, el("span", { class: "fecha" }, new Date(t.creado).toLocaleDateString("es-CL", { dateStyle: "short" })),
      " ", el("span", { class: "hora" }, new Date(t.creado).toLocaleTimeString("es-CL", { timeStyle: "short" }))),
    el("td", {}, nombreFlujo(t)),
    el("td", {}, valor(t.argumentos)),
    el("td", {}, insigniaModo(t)),
    el("td", {}, el("span", { class: `estado ${t.estado}` }, t.estado)),
    el("td", { class: "col-costo" }, costoCorto(costos.get(t.id))),
    el("td", { class: "col-quien" }, t.pedido_por));
    nodo.replaceChildren(
      el("h4", {}, "Últimos trabajos"),
      el("div", { class: "tabla-envoltura" }, el("table", { class: "historial" },
        el("thead", {}, el("tr", {}, ["Cuándo", "Qué", titulo, "Modo", "Estado"].map((c) => el("th", {}, c)),
          el("th", { class: "col-costo" }, "API"), el("th", { class: "col-quien" }, "Quién"))),
        el("tbody", {}, lista.map(fila)))));
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
  // El script deja la lista siempre, aunque esté vacía. Que falte el archivo
  // o no se pueda leer es otra cosa que "no hay nada": no se confunden.
  const otraVez = `Vuelve a simular para elegir cuáles ${verbo.toLowerCase()}.`;
  const noPude = (motivo) => nodo.replaceChildren(caja("aviso", `No pude leer la lista de respuestas de esta simulación `
    + `(${motivo}). ${otraVez}`));
  fetch(url, { cache: "no-store" }).then(async (r) => {
    if (r.status === 404) {
      nodo.replaceChildren(caja("aviso", `No encontré la lista de respuestas que debía dejar esta simulación. ${otraVez}`));
      return;
    }
    if (!r.ok) { noPude(mensajeDeError(r.status)); return; }
    const lista = await r.json();
    if (!Array.isArray(lista)) { noPude("el archivo no tiene el formato esperado"); return; }
    if (!lista.length) {
      nodo.replaceChildren(caja("info", `Ninguna respuesta nueva: la simulación no encontró nada que ${verbo.toLowerCase()}.`));
      return;
    }
    const casillas = lista.map((c) => el("input", { type: "checkbox", checked: !c.ya_tiene_nota, value: c.correo }));
    const boton = el("button", { class: "primario real", type: "button" });
    const actualizar = () => {
      const n = casillas.filter((x) => x.checked).length;
      boton.textContent = n === 0 ? `${verbo}: marca al menos una`
        : `${verbo} ${n === 1 ? "la elegida" : `las ${n} elegidas`} y mandar feedback`;
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
      el("p", { class: "nota-pie" }, "Las no marcadas quedan pendientes."),
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
  }).catch(() => noPude("no hubo conexión o el archivo vino dañado"));
  return nodo;
}
