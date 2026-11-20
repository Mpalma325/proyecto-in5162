// Lo que comparten todas las páginas del sitio: armar elementos, hablar con la
// API, la barra de navegación y cómo se muestra la salida de un trabajo.

import { formatoUsd, leerConsumo, leerPrecios, notaMezcla, sumarConsumo, textoConsumo } from "./consumo.js";

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

/** Sin tildes ni mayúsculas, para buscar: "perez" encuentra a Pérez. */
export const normalizar = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

let dialogos = 0;

/**
 * Pide confirmar algo dentro de la página, en lugar del confirm del navegador. El foco
 * parte en «Cancelar»: un Enter apurado no manda nada, y Esc también cancela.
 * `tono` pinta el botón de la acción ("real" o "peligro", como los primarios).
 * Devuelve una promesa: true si se eligió `accion`.
 */
export function confirmar(texto, accion = "Aceptar", tono = "") {
  return new Promise((resolver) => {
    const id = `texto-confirmar-${++dialogos}`;
    const cancelar = el("button", { class: "secundario", type: "submit", value: "no" }, "Cancelar");
    const dialogo = el("dialog", { class: "confirmar", "aria-describedby": id, "aria-label": accion },
      el("form", { method: "dialog" },
        el("p", { class: "texto-confirmar", id }, texto),
        el("div", { class: "acciones" }, cancelar,
          el("button", { class: `primario ${tono}`.trim(), type: "submit", value: "si" }, accion))));
    // Esc cierra el diálogo sin valor: cuenta como cancelar.
    dialogo.addEventListener("close", () => {
      dialogo.remove();
      resolver(dialogo.returnValue === "si");
    });
    document.body.append(dialogo);
    dialogo.showModal();
    cancelar.focus();
  });
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
// ---------------------------------------------------------------- tema

// "sistema" (sigue al computador), "claro" u "oscuro". Se recuerda en este
// navegador; si no se puede guardar, queda el del sistema.
const TEMAS = ["sistema", "claro", "oscuro"];
function leerTema() {
  try { return TEMAS.includes(localStorage.getItem("tema")) ? localStorage.getItem("tema") : "sistema"; } catch { return "sistema"; }
}
function aplicarTema(tema) {
  if (tema === "sistema") delete document.documentElement.dataset.tema;
  else document.documentElement.dataset.tema = tema;
}
if (typeof document !== "undefined" && document.documentElement) aplicarTema(leerTema());

/** Si la página se ve en oscuro ahora, por elección o por el sistema. Lo usan los gráficos. */
export function esOscuro() {
  const t = document.documentElement.dataset.tema;
  return t ? t === "oscuro" : matchMedia("(prefers-color-scheme: dark)").matches;
}

function botonTema() {
  const nombre = { sistema: "Tema: sistema", claro: "Tema: claro", oscuro: "Tema: oscuro" };
  const b = el("button", { class: "tema", type: "button", title: "Cambiar entre sistema, claro y oscuro" },
    nombre[leerTema()]);
  b.addEventListener("click", () => {
    const sigue = TEMAS[(TEMAS.indexOf(leerTema()) + 1) % TEMAS.length];
    try { localStorage.setItem("tema", sigue); } catch { /* queda solo en esta vista */ }
    aplicarTema(sigue);
    b.textContent = nombre[sigue];
    window.dispatchEvent(new Event("cambio-tema"));
  });
  return b;
}

export function navegacion() {
  // Cloudflare sirve las páginas sin ".html" (tests.html se ve en /tests).
  const aqui = location.pathname.replace(/\.html$/, "").replace(/^\/index$/, "/");
  const nav = el("nav", { class: "navegacion" }, PAGINAS.map(([ruta, nombre]) =>
    el("a", { href: ruta, "aria-current": ruta === aqui ? "page" : null }, nombre)), botonTema(),
    // Cloudflare Access corta la sesión en esta dirección y vuelve a pedir el correo.
    el("a", { href: "/cdn-cgi/access/logout", class: "salir" }, "Cerrar sesión"));
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
  // Lo que se desliza en celular es cada fila de pasos, no la barra entera.
  for (const fila of [barra, ...barra.querySelectorAll(".fila-pestanas")]) centrarSeleccion(fila);
  return barra;
}

const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const dos = (n) => String(n).padStart(2, "0");

/** "lun 19/10" y "10:15": las dos mitades de fechaCorta, para mostrarlas por separado. */
export const diaCorto = (fecha) => `${DIAS[fecha.getDay()]} ${dos(fecha.getDate())}/${dos(fecha.getMonth() + 1)}`;
export const horaCorta = (fecha) => `${fecha.getHours()}:${dos(fecha.getMinutes())}`;

/** "lun 19/10, 10:15" (sin la hora si es fin del día). */
export function fechaCorta(fecha) {
  if (!fecha) return "";
  const finDelDia = fecha.getHours() === 23 && fecha.getMinutes() === 59;
  return finDelDia ? diaCorto(fecha) : `${diaCorto(fecha)}, ${horaCorta(fecha)}`;
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

// ---------------------------------------------------------------- texto de correos
// Lo que se leyó del buzón viene cortado cada ~75 caracteres, como lo parte un
// cliente de correo: el párrafo quedaba roto en líneas a media frase.

const ITEM = /^\s*([-*•]|\d+[.)]|[A-Za-z][.)]|P\d+\.?)(\s|$)/;
const ETIQUETA = /^\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{2,40}):\s*(.*)$/;

/** Une las líneas que el correo cortó por largo; deja los saltos de verdad. */
export function desenvolver(texto) {
  const lineas = String(texto ?? "").replace(/\r\n?/g, "\n").split("\n");
  const salida = [];
  for (const linea of lineas) {
    const previa = salida[salida.length - 1];
    // Es la continuación de la misma frase si la línea anterior no cerró la
    // frase y esta no abre un ítem ni una etiqueta, y además la anterior tiene
    // el largo de un corte automático o esta sigue en minúscula. Algunos
    // clientes vuelven a cortar lo ya cortado y dejan una línea larga seguida
    // de una o dos palabras ("…es solo 8" / "eventos por unidad").
    const continua = previa !== undefined && previa.trim() && !/[.:;!?]$/.test(previa.trimEnd())
      && linea.trim() && !ITEM.test(linea) && !ETIQUETA.test(linea);
    const corte = continua && ((previa.length >= 55 && previa.length <= 80) || /^\s*[a-záéíóúñü(“"]/.test(linea));
    if (corte) salida[salida.length - 1] = `${previa.trimEnd()} ${linea.trim()}`;
    else salida.push(linea);
  }
  return salida.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

/**
 * La respuesta del alumno para leerla: sin cortes de línea y sin el
 * "El vie, … escribió:" que algunos clientes dejan al final, antes de la cita.
 */
export const respuestaLegible = (texto) =>
  desenvolver(texto).replace(/\n*\s*(El|On) [^\n]{5,160}(escribió|wrote):\s*$/, "").trimEnd();

/**
 * Una corrección guardada como texto (las recuperadas del buzón) vuelta al
 * formato del correo: "RESPUESTA:" sola en su línea y el contenido abajo era
 * <b>RESPUESTA:</b> contenido en el original.
 */
export function evaluacionDeTexto(texto) {
  const lineas = desenvolver(texto).split("\n");
  const parrafos = [];
  let actual = [];
  const cerrar = () => { if (actual.length) parrafos.push(`<p>${actual.join("<br>\n")}</p>`); actual = []; };
  for (let i = 0; i < lineas.length; i++) {
    const linea = lineas[i].trim();
    if (!linea) { cerrar(); continue; }
    if (/^EVALUACI[OÓ]N SEG[UÚ]N PAUTA:?$/i.test(linea)) { cerrar(); parrafos.push(`<p><strong>${escapar(linea)}</strong></p>`); continue; }
    if (/^(P\d+|[A-Z])\.$/.test(linea)) { cerrar(); actual.push(`<u>${escapar(linea)}</u>`); continue; }
    const m = linea.match(ETIQUETA);
    if (m) {
      let valor = m[2];
      // El valor venía en la línea siguiente.
      if (!valor && lineas[i + 1]?.trim() && !ETIQUETA.test(lineas[i + 1])) valor = lineas[++i].trim();
      if (/^(NOTA FINAL|PUNTAJE TOTAL|ORIGINALIDAD|JUSTIFICACI[OÓ]N ORIGINALIDAD|RETROALIMENTACI[OÓ]N)$/.test(m[1])) cerrar();
      actual.push(`<b>${escapar(m[1])}:</b> ${escapar(valor)}`);
      continue;
    }
    actual.push(escapar(linea));
  }
  cerrar();
  return parrafos.join("\n");
}

// ---------------------------------------------------------------- correos
// Un correo se muestra como lo ve el alumno en Gmail: el HTML dibujado, no sus
// etiquetas. Va en un iframe sin scripts (como Gmail, que tampoco los corre);
// allow-same-origin solo deja medir el alto para que no quede barra de scroll.

const escapar = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

/**
 * El documento del iframe: la letra y los márgenes de un correo abierto en
 * Gmail. El cuerpo va tal cual se envió. La corrección viene del modelo, que
 * lee texto del alumno: nada se pide afuera (ni imágenes ni CSS remotos), para
 * que una respuesta manipulada no avise a nadie cuándo se abre la ficha.
 */
function documentoCorreo(cuerpo, html) {
  const contenido = html ? String(cuerpo) : `<div style="white-space:pre-wrap">${escapar(cuerpo)}</div>`;
  return `<!doctype html><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<base target="_blank">
<style>html{background:#fff}body{margin:0;padding:4px 2px;font:small Arial,Helvetica,sans-serif;color:#222;
overflow-wrap:anywhere}img{max-width:100%}</style>${contenido}`;
}

// El último alto de cada correo. Mientras un trabajo corre la salida se
// redibuja cada 1,5 s y los iframes se rehacen: parten con su alto ya medido
// y la página no salta.
const altosCorreo = new Map();

function ajustarAlto(iframe) {
  const clave = iframe.getAttribute("srcdoc");
  if (altosCorreo.has(clave)) iframe.style.height = altosCorreo.get(clave);
  const medir = () => {
    const doc = iframe.contentDocument;
    // Antes de cargar, el iframe tiene un about:blank vacío: medirlo daría 0.
    if (!doc?.documentElement || doc.URL !== "about:srcdoc" || !iframe.clientWidth) return;
    // Se mide con el iframe en 0: así un cuerpo con 100vh o height:100% no
    // crece con cada medida, y el alto puede bajar si el contenido se achica.
    const antes = iframe.style.height;
    iframe.style.height = "0px";
    const alto = `${Math.ceil(doc.documentElement.scrollHeight)}px`;
    iframe.style.height = antes;
    altosCorreo.set(clave, alto);
    if (antes !== alto) iframe.style.height = alto;
  };
  iframe.addEventListener("load", medir);
  // Dentro de un <details> cerrado el iframe no tiene ancho: se mide al abrirse.
  new ResizeObserver(medir).observe(iframe);
}

/**
 * `{asunto, para, nombre, de, cuerpo, html, enviado}`: lo que deja la línea
 * `@@correo` de un trabajo (modulos/mail/vista.py). `aviso` va bajo la cabecera.
 */
export function vistaCorreo(c, { aviso } = {}) {
  const iframe = el("iframe", {
    class: "cuerpo-correo", title: c.asunto || "Correo",
    sandbox: "allow-same-origin allow-popups allow-popups-to-escape-sandbox", referrerpolicy: "no-referrer",
    srcdoc: documentoCorreo(c.cuerpo || "", c.html),
  });
  ajustarAlto(iframe);
  const para = c.nombre ? `${c.nombre} <${c.para}>` : c.para;
  return el("article", { class: "correo-gmail" },
    c.asunto ? el("h4", { class: "asunto-correo" }, c.asunto) : null,
    el("p", { class: "cabecera-correo" },
      c.de ? [el("strong", {}, c.de), " "] : null,
      para ? el("span", { class: "tenue" }, `para ${para}`) : null,
),
    aviso ? el("p", { class: "aviso-correo tenue" }, aviso) : null,
    iframe);
}

const MARCA_CORREO = "@@correo ";

/**
 * La salida de un trabajo con sus correos dibujados: el texto va coloreado
 * como siempre y cada línea `@@correo` se vuelve un correo plegable. Sin
 * correos es la caja de siempre; con correos, una caja más alta, para no leer
 * un correo entero dentro de un scroll chico.
 */
export function salidaConCorreos(texto, clase = "salida") {
  if (!texto.split("\n").some((l) => l.startsWith(MARCA_CORREO))) return salidaColoreada(texto, clase);
  const partes = [];
  let lineas = [];
  let correos = null;
  const cerrarTexto = () => {
    if (lineas.join("").trim()) partes.push(salidaColoreada(lineas.join("\n").replace(/^\n+|\n+$/g, ""), clase));
    lineas = [];
  };
  for (const linea of texto.split("\n")) {
    let c = null;
    if (linea.startsWith(MARCA_CORREO)) {
      try { c = JSON.parse(linea.slice(MARCA_CORREO.length)); } catch { c = null; }
    }
    if (!c) {
      if (linea.trim()) correos = null;
      lineas.push(linea);
      continue;
    }
    cerrarTexto();
    if (!correos) {
      correos = el("div", { class: "correos-trabajo" });
      partes.push(correos);
    }
    correos.append(el("details", { class: "correo-plegable" },
      el("summary", {}, el("span", { class: "tenue" }, c.enviado ? "Enviado a " : "Para "),
        c.nombre || c.para, el("span", { class: "tenue" }, ` · ${c.asunto}`)),
      vistaCorreo(c)));
  }
  cerrarTexto();
  return el("div", { class: `${clase} con-correos` }, partes);
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

/**
 * El test de un trabajo: `instancia` en los semestres nuevos, `semana` en los
 * de antes (preguntas.csv con columna Semana). Los dos son el Item de notas.csv.
 */
export const idDe = (a) => a?.instancia ?? a?.semana;

// Cómo se llama cada instancia («Control 2»): el id no lo ve el docente. Lo
// llenan las páginas que leen preguntas.csv (preguntas.js, nombrarInstancias).
let nombresInstancias = new Map();
export function nombrarInstancias(nombres) { nombresInstancias = new Map(nombres); }
export const nombreInstancia = (n) => nombresInstancias.get(Number(n)) || `instancia ${n}`;

/** "semana 4", "Control 2", "T2" o nada: lo que distingue a un trabajo de otro del mismo flujo. */
export function sobreQue(a) {
  if (a.tarea) return a.tarea;
  if (a.instancia) return nombreInstancia(a.instancia);
  if (a.semana) return `semana ${a.semana}`;
  return "";
}

const sinPrefijo = (flujo) => flujo.replace(/^[a-z]+\./, "");

// Cómo se llama cada flujo en pantalla: el nombre de su pestaña. El id no cambia.
const NOMBRE_FLUJO = {
  "tests.enviar": "Enviar preguntas", "tests.evaluar": "Evaluar respuestas", "tests.feedback": "Mandar feedback",
  "tests.resumen": "Resumen semana",
  "tests.tutoria": "Responder dudas", "tests.experimento": "Probar criterio",
  "tareas.chequeo": "Revisar entregas", "tareas.generar": "Generar preguntas", "tareas.enviar": "Enviar preguntas",
  "tareas.recolectar": "Recolectar respuestas", "tareas.corregir": "Corregir", "tareas.segunda": "Segunda oportunidad",
  "tareas.feedback": "Mandar correcciones",
  "datos.ajustar": "Ajustar nota", "datos.sabana": "Armar la sábana", "datos.panel": "Actualizar los resultados",
};

export function nombreFlujo(t) {
  const nombre = NOMBRE_FLUJO[t.flujo] || sinPrefijo(t.flujo);
  const paso = t.flujo === "tareas.segunda" && t.argumentos?.paso;
  return paso ? `${nombre} (${paso})` : nombre;
}

// ---------------------------------------------------------------- registro de ediciones

/** El encabezado que le dice al sitio qué cambió, para el registro (Configuración › Registro). */
export const conDetalle = (texto) => ({ "x-in5162-detalle": encodeURIComponent(String(texto || "").slice(0, 380)) });

/** Qué dice una fila del registro: lo que contó la página, o el trabajo que escribió el archivo. */
export function textoEdicion(e) {
  if (!e.detalle) return "";
  try {
    const j = JSON.parse(e.detalle);
    if (j && j.flujo) {
      const args = j.argumentos || {};
      return [nombreFlujo({ flujo: j.flujo, argumentos: args }), sobreQue(args), j.prueba ? "simulación" : null]
        .filter(Boolean).join(" · ");
    }
  } catch { /* es texto */ }
  return e.detalle;
}

/** "2 filas agregadas, 1 cambiada": qué cambió entre dos versiones de una tabla, fila por fila. */
export function resumenCsv(columnas, antes, despues) {
  const k = Math.max(0, columnas.findIndex((c) => /correo/i.test(c)));
  const clave = (f) => String(f[k] ?? "").trim().toLowerCase();
  const a = new Map(antes.map((f) => [clave(f), JSON.stringify(f)]));
  const d = new Map(despues.map((f) => [clave(f), JSON.stringify(f)]));
  const agregadas = [...d.keys()].filter((x) => !a.has(x)).length;
  const quitadas = [...a.keys()].filter((x) => !d.has(x)).length;
  const cambiadas = [...d.keys()].filter((x) => a.has(x) && a.get(x) !== d.get(x)).length;
  const n = (c, uno, varios) => `${c} ${c === 1 ? uno : varios}`;
  const partes = [agregadas && n(agregadas, "fila agregada", "filas agregadas"),
    quitadas && n(quitadas, "fila quitada", "filas quitadas"),
    cambiadas && n(cambiadas, "fila cambiada", "filas cambiadas")].filter(Boolean);
  return partes.length ? partes.join(", ") : "sin cambios en las filas";
}

// Los flujos cuyo modo prueba es una simulación: no mandan correos ni guardan
// notas. Los demás (resumen, generar, recolectar, preparar...) quedan con
// prueba = 1 porque nadie lo pide en falso, pero sí llaman al modelo o
// escriben archivos: de ellos no se puede decir "no se hizo nada".
const SIMULABLES = new Set(["tests.enviar", "tests.evaluar", "tests.feedback", "tests.tutoria", "tests.experimento",
  "tareas.enviar", "tareas.corregir", "tareas.feedback"]);
const simula = (t) => (t.flujo === "tareas.segunda" ? t.argumentos?.paso === "enviar" : SIMULABLES.has(t.flujo));

/** Si el trabajo fue una simulación: no mandó correos ni guardó notas. */
export const esSimulacion = (t) => Boolean(t.prueba) && simula(t);

// Un trabajo y su repetición: mismo flujo, misma semana (o instancia) o tarea, mismo paso.
const claveTrabajo = (t) => [t.flujo, idDe(t.argumentos) ?? "", t.argumentos?.tarea ?? "", t.argumentos?.paso ?? ""]
  .join("|");

/**
 * Trabajos reales que fallaron y no se volvieron a correr bien. Una simulación
 * fallida no hizo nada, y un fallo que después se repitió con éxito ya está
 * resuelto: ninguno de los dos se marca. Si el mismo trabajo falló varias
 * veces, queda el intento más reciente, con `intentos` = cuántas veces falló.
 */
export function fallidosSinResolver(trabajos) {
  const fallidos = trabajos.filter((t) => t.estado === "fallido" && !esSimulacion(t)
    && !trabajos.some((o) => o.estado === "terminado" && !esSimulacion(o) && claveTrabajo(o) === claveTrabajo(t)
      && new Date(o.creado) > new Date(t.creado)))
    .sort((a, b) => new Date(b.creado) - new Date(a.creado));
  const porClave = new Map();
  for (const t of fallidos) {
    const k = claveTrabajo(t);
    if (porClave.has(k)) porClave.get(k).intentos += 1;
    else porClave.set(k, { ...t, intentos: 1 });
  }
  return [...porClave.values()];
}

/**
 * La hora a la que se programó un trabajo que todavía espera (Date), o null.
 * Un envío de tareas programado, y la recolección y la corrección que lo siguen,
 * quedan "pendiente" hasta esa hora (motor/cola.py).
 */
export function programadoPara(t, ahora = Date.now()) {
  if (t.estado !== "pendiente" || !t.argumentos?.a_las) return null;
  const d = new Date(t.argumentos.a_las);
  return Number.isNaN(d.getTime()) || d.getTime() <= ahora - 60_000 ? null : d;
}

/** "hoy 10:00", "mañana 10:00" o "vie 14/11 10:00". */
export function textoProgramado(d, ahora = new Date()) {
  const dia = (x) => x.toDateString();
  const manana = new Date(ahora.getTime() + 86_400_000);
  const cuando = dia(d) === dia(ahora) ? "hoy" : dia(d) === dia(manana) ? "mañana" : diaCorto(d);
  return `${cuando} ${horaCorta(d)}`;
}

// Desde cuándo corre un trabajo: si se programó, desde esa hora, no desde que se pidió.
function inicioDe(t) {
  const creado = new Date(t.creado).getTime();
  const a_las = t.argumentos?.a_las ? new Date(t.argumentos.a_las).getTime() : NaN;
  return Number.isNaN(a_las) ? creado : Math.max(creado, a_las);
}

/**
 * Si el trabajo, corrido de verdad, manda correos a los alumnos. tests.evaluar
 * cuenta también en modo revisión: manda el correo de duplicado a quien
 * responde dos veces. El ajuste de nota escribe solo con «Avisarle al alumno».
 */
function mandaCorreos(t) {
  if (t.flujo === "datos.ajustar") return !t.prueba && t.argumentos?.avisar === true;
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

/**
 * La barra: cuántos van de cuántos. Queda a la vista al terminar, también en una
 * simulación (que dura un segundo) o en un trabajo detenido a medio camino.
 */
function barraProgreso(t) {
  const a = avanceDe(t, t.estado === "pendiente" ? null : progresoDe(t.salida));
  if (!a) return null;
  return el("div", {
    class: "progreso-trabajo", role: "progressbar",
    "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(a.pct),
  },
    el("div", { class: "barra-progreso" }, el("span", { style: `width: ${a.pct}%` })),
    el("span", { class: "texto-progreso" }, a.texto));
}

// Los últimos trabajos que vio la página: de ahí sale cuánto suele tardar cada tipo.
let historialVisto = [];

const promedio = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

/** Cuánto tardaron en promedio, en ms, los últimos 10 del mismo tipo y modo que terminaron. */
function duracionTipica(t) {
  const iguales = historialVisto.filter((o) => o.id !== t.id && o.flujo === t.flujo
    && Boolean(o.prueba) === Boolean(t.prueba) && o.estado === "terminado").slice(0, 10);
  return promedio(iguales.map((o) => new Date(o.actualizado) - inicioDe(o)).filter((d) => d > 0));
}

function textoRestante(ms) {
  if (ms <= 0) return "terminando…";
  const s = Math.ceil(ms / 1000);
  return s < 60 ? `quedan ~${s} s` : `quedan ~${Math.ceil(s / 60)} min`;
}

/**
 * Cuánto va y cuánto le queda. Con alumnos ya contados, al ritmo que lleva; si
 * todavía prepara o no recorre alumnos, según lo que tardaron los anteriores del
 * mismo tipo (la barra avanza con el reloj). Al terminar, lo que alcanzó a hacer.
 */
export function avanceDe(t, p, ahora = Date.now()) {
  const cuenta = p && p.total ? `${p.hechos}/${p.total}${p.unidad ? ` ${p.unidad}` : ""}` : "";
  if (t.estado === "pendiente") return null;
  if (ESTADOS_FINALES.has(t.estado)) {
    return cuenta ? { pct: Math.min(100, Math.round((p.hechos / p.total) * 100)), texto: cuenta, final: true } : null;
  }
  const pasado = ahora - inicioDe(t);
  let total = null;
  if (p && p.total && p.hechos > 0 && p.hechos < p.total) total = (pasado * p.total) / p.hechos;
  else total = duracionTipica(t);
  const pctCuenta = p && p.total ? (p.hechos / p.total) * 100 : 0;
  const pctReloj = total ? Math.min(95, (pasado / total) * 100) : 0;
  if (!total && !cuenta) return null;
  const pct = Math.round(Math.max(pctCuenta, pctReloj));
  return { pct, texto: [cuenta, total ? textoRestante(total - pasado) : null].filter(Boolean).join(" · ") };
}

function vistaTrabajo(t, extra, precios = {}) {
  const simulacion = Boolean(t.prueba) && simula(t);
  const [tecnico, resto] = separarTecnico(sinProgreso(t.salida));
  const cuenta = contarLineas(resto);
  const conteo = CONTEO_SALIDA.filter(([s]) => cuenta[s])
    .flatMap(([s, clase, texto], i) => [i ? " · " : "", el("span", { class: `l-${clase}` }, `${s} ${texto(cuenta[s], simulacion)}`)]);
  const detalle = [nombreFlujo(t), sobreQue(t.argumentos || {}), `pedido por ${t.pedido_por}`]
    .filter(Boolean).join(" · ");
  const programado = programadoPara(t);
  const esperando = programado ? `Programado para ${textoProgramado(programado)}. Hasta esa hora se puede detener.`
    : t.estado === "pendiente" ? "Esperando que el motor lo tome…"
    : t.estado === "cancelando" ? "Deteniéndose…"
      : ESTADOS_FINALES.has(t.estado) ? "(el trabajo no dejó salida)" : "Corriendo…";
  return [
    el("p", { class: "cabeza-trabajo" }, etiquetaEstado(t), " ", insigniaModo(t), " ",
      el("span", { class: "tenue" }, detalle), botonDetener(t)),
    simulacion && t.estado !== "fallido"
      ? el("p", { class: "titulo-salida" }, "Esto es lo que pasaría (no se hizo nada)") : null,
    barraProgreso(t),
    conteo.length ? el("p", { class: "resumen-salida" }, "En la salida: ", conteo) : null,
    consumoDe(t, precios),
    tecnico ? el("details", { class: "detalle-tecnico" }, el("summary", {}, "Detalle técnico"),
      salidaColoreada(tecnico, "salida tecnica")) : null,
    resto.trim() ? salidaConCorreos(resto) : salidaColoreada(esperando),
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
  const programado = programadoPara(t);
  return el("button", {
    class: "enlace detener", type: "button",
    onclick: async (e) => {
      const boton = e.currentTarget;
      if (!await confirmar(programado ? `¿Cancelar este trabajo programado para ${textoProgramado(programado)}? No va a correr.`
        : "¿Detener este trabajo? Para antes del alumno siguiente; lo que ya hizo queda guardado.",
      programado ? "Anular el trabajo" : "Detener", "peligro")) return;
      boton.disabled = true;
      try {
        await api(`/api/trabajos/${t.id}/cancelar`, { method: "POST" });
      } catch (err) {
        alert(`No pude detenerlo: ${err.message}`);
        boton.disabled = false;
      }
    },
  }, programado ? "Cancelar" : "Detener");
}

/** El estado de un trabajo; uno programado dice para cuándo. */
function etiquetaEstado(t) {
  const programado = programadoPara(t);
  return programado
    ? el("span", { class: "estado pendiente", title: "Corre solo a esa hora" }, `programado · ${textoProgramado(programado)}`)
    : el("span", { class: `estado ${t.estado}` }, t.estado);
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
  const correosAbiertos = [...destino.querySelectorAll("details.correo-plegable")].map((d) => d.open);
  const previa = destino.querySelector(":scope > .salida:not(.tecnica)");
  const arriba = previa ? previa.scrollTop : 0;
  const alFinal = !previa || previa.scrollTop + previa.clientHeight >= previa.scrollHeight - 30;
  destino.replaceChildren(...vistaTrabajo(t, extra, precios));
  if (abierto) destino.querySelector("details.detalle-tecnico")?.setAttribute("open", "");
  destino.querySelectorAll("details.correo-plegable").forEach((d, i) => { if (correosAbiertos[i]) d.open = true; });
  // Sigue la cola de la salida solo si quien mira ya estaba al final: si subió
  // a leer un correo, no se le mueve.
  const caja = destino.querySelector(":scope > .salida:not(.tecnica)");
  if (caja) caja.scrollTop = alFinal ? caja.scrollHeight : arriba;
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
/** La barra chica de una fila de la tabla: "12/36". */
function avanceEnFila(t) {
  const a = avanceDe(t, t.progreso);
  if (!a) return null;
  return el("span", { class: "avance-fila", title: a.texto },
    el("span", { class: "barra-progreso" }, el("span", { style: `width: ${a.pct}%` })), a.texto);
}

/** El costo de un trabajo en la tabla: dólares si hay precio, tokens si no, nada si no llamó al modelo. */
function costoCorto(total) {
  if (!total || !total.llamadas) return "";
  if (total.sinPrecio.length && !total.usd) return `${(total.entrada + total.salida).toLocaleString("es-CL")} tokens`;
  // Un modelo con su US$ del momento y otro calculado hoy: se marca, y la leyenda va bajo la tabla.
  const nota = notaMezcla(total);
  return nota ? el("span", { title: nota }, `${formatoUsd(total.usd)}*`) : formatoUsd(total.usd);
}

// Cuántos trabajos pide el historial de entrada, y cuántos suma cada "Ver más"
// (el Worker no entrega más de 120).
const HISTORIAL_INICIAL = 30;
const HISTORIAL_MAXIMO = 120;

/** La URL de la lista de trabajos: `prefijo` ("tareas.") deja solo los de esa página. */
export function urlTrabajos(semestre, prefijo = "", limite = HISTORIAL_INICIAL, soloPendientes = false) {
  const q = new URLSearchParams({ semestre });
  if (prefijo) q.set("flujo", prefijo);
  if (soloPendientes) q.set("pendientes", "1");
  else if (limite !== HISTORIAL_INICIAL) q.set("limite", String(limite));
  return `/api/trabajos?${q}`;
}

export function historialTrabajos({ incluye, columna, alElegir, prefijo = "" }) {
  const nodo = el("div");
  let limite = HISTORIAL_INICIAL;
  let ultimoSemestre = "";
  async function dibujar(semestre) {
    clearTimeout(nodo._refresco);
    if (semestre !== ultimoSemestre) { limite = HISTORIAL_INICIAL; ultimoSemestre = semestre; }
    let lista = [];
    let costos = new Map();
    let trabajos = [];
    try {
      let consumo, precios;
      [trabajos, consumo, precios] = await Promise.all([
        api(urlTrabajos(semestre, prefijo, limite)),
        api(`/api/consumo/${encodeURIComponent(semestre)}`).catch(() => []),
        preciosApi()]);
      historialVisto = trabajos;
      lista = trabajos.filter(incluye);
      costos = new Map(consumo.map((c) => [c.id, sumarConsumo(leerConsumo(c.lineas.join("\n")), precios)]));
    } catch {
      return;
    }
    if (!lista.length) { nodo.replaceChildren(); return; }
    // Mientras haya algo en la fila o corriendo, la tabla se pone al día sola:
    // así se ve avanzar cada trabajo, también varias simulaciones a la vez.
    // Uno programado para más tarde no necesita mirarse cada 3 segundos.
    const activos = lista.filter((t) => !ESTADOS_FINALES.has(t.estado));
    if (activos.length) {
      const espera = activos.every((t) => programadoPara(t)) ? 30_000 : 3000;
      nodo._refresco = setTimeout(() => { if (nodo.isConnected) dibujar(semestre); }, espera);
    }
    const [titulo, valor] = columna;
    // La fila entera abre el trabajo, también con el teclado (Tab y Enter).
    const fila = (t) => el("tr", {
      tabindex: "0", title: "Ver la salida de este trabajo", onclick: () => alElegir(t),
      onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); alElegir(t); } },
    },
    // Fecha y hora por separado: en el celular cada una va en su línea, sin cortarse.
    // Mismo formato que el resto del sitio (fechaCorta): "dom 01/11" y "22:37".
    el("td", {}, el("span", { class: "fecha" }, diaCorto(new Date(t.creado))),
      " ", el("span", { class: "hora" }, horaCorta(new Date(t.creado)))),
    el("td", {}, nombreFlujo(t)),
    el("td", {}, valor(t.argumentos)),
    el("td", {}, insigniaModo(t)),
    el("td", {}, etiquetaEstado(t), avanceEnFila(t)),
    el("td", { class: "col-costo" }, costoCorto(costos.get(t.id))),
    el("td", { class: "col-quien" }, t.pedido_por));
    nodo.replaceChildren(
      el("h4", {}, "Últimos trabajos"),
      el("div", { class: "tabla-envoltura" }, el("table", { class: "historial" },
        el("thead", {}, el("tr", {}, ["Cuándo", "Qué", titulo, "Modo", "Estado"].map((c) => el("th", {}, c)),
          el("th", { class: "col-costo" }, "API"), el("th", { class: "col-quien" }, "Quién"))),
        el("tbody", {}, lista.map(fila)))),
      // replaceChildren (a diferencia de el()) escribe un null como el texto "null".
      ...(lista.some((t) => notaMezcla(costos.get(t.id) || {})) ? [el("p", { class: "nota-pie" },
        "* Parte del costo se calculó con los precios de hoy.")] : []),
      // Si llegaron tantos como se pidieron, puede haber más atrás.
      ...(trabajos.length >= limite && limite < HISTORIAL_MAXIMO ? [el("div", { class: "acciones" },
        el("button", { class: "secundario", type: "button", onclick: () => {
          limite = Math.min(limite + HISTORIAL_INICIAL * 2, HISTORIAL_MAXIMO);
          dibujar(semestre);
        } }, "Ver más"))] : []));
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
 * `alProcesar(correos)` pide el trabajo real con esa lista. Con
 * `mandaFeedback: false` el trabajo real deja las correcciones para revisarlas
 * antes de mandarlas, y los textos lo dicen.
 *
 * Quien respondió fuera de plazo (tareas) viene marcado y sin elegir: se
 * corrige solo si alguien lo marca. Lo mismo quien ya está corregido (con
 * nota, por revisar o descartado): `estadoCandidato` lo dice.
 *
 * `textoConfirmar(nombres)`, si se pasa, reemplaza el texto de la
 * confirmación. `aMano`, si se pasa, agrega «Las corrijo yo»: pide el trabajo
 * con `alProcesar(elegidos, { sin_modelo: true })`.
 */
export function elegirCandidatos({ semestre, ruta, verbo, alProcesar, mandaFeedback = true, textoConfirmar,
  aMano = false }) {
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
    const casillas = lista.map((c) => el("input", { type: "checkbox", checked: !estadoCandidato(c) && !c.fuera_de_plazo,
      value: c.correo }));
    const boton = el("button", { class: "primario real", type: "button" });
    const actualizar = () => {
      const n = casillas.filter((x) => x.checked).length;
      boton.textContent = n === 0 ? `${verbo}: marca al menos una`
        : `${verbo} ${n === 1 ? "la elegida" : `las ${n} elegidas`}${mandaFeedback ? " y mandar feedback" : ""}`;
      boton.disabled = n === 0;
      if (manual) manual.disabled = n === 0;
    };
    const manual = aMano ? el("button", { class: "secundario", type: "button" }, "Las corrijo yo") : null;
    casillas.forEach((x) => x.addEventListener("change", actualizar));
    const todas = (v) => { casillas.forEach((x) => { x.checked = v; }); actualizar(); };
    const aviso = el("div");
    boton.addEventListener("click", async () => {
      const elegidos = casillas.filter((x) => x.checked).map((x) => x.value);
      const nombres = lista.filter((c) => elegidos.includes(c.correo)).map((c) => c.nombre).join(", ");
      if (!await confirmar(textoConfirmar ? textoConfirmar(nombres) : mandaFeedback
        ? `Vas a ${verbo.toLowerCase()} y mandarle el feedback por correo a: ${nombres}.\n\nLas demás quedan como están. ¿Confirmas?`
        : `Vas a ${verbo.toLowerCase()} a: ${nombres}.\n\nLas notas quedan guardadas y las correcciones esperan tu `
          + "revisión antes de mandarse. Las demás quedan como están. ¿Confirmas?",
      mandaFeedback ? `${verbo} y mandar` : verbo, "real")) return;
      boton.disabled = true;
      aviso.replaceChildren();
      try {
        await alProcesar(elegidos);
      } catch (e) {
        aviso.replaceChildren(caja("aviso", `No pude pedir el trabajo: ${e.message}`));
        boton.disabled = false;
      }
    });
    manual?.addEventListener("click", async () => {
      const elegidos = casillas.filter((x) => x.checked).map((x) => x.value);
      const nombres = lista.filter((c) => elegidos.includes(c.correo)).map((c) => c.nombre).join(", ");
      if (!await confirmar(`Vas a dejar para corregir a mano a: ${nombres}.\n\nNo se llama al modelo y no sale `
        + "feedback: cada una queda vacía en Tests › Revisar para que la corrijas ahí. ¿Confirmas?",
      "Las corrijo yo", "real")) return;
      manual.disabled = true;
      aviso.replaceChildren();
      try {
        await alProcesar(elegidos, { sin_modelo: true });
      } catch (e) {
        aviso.replaceChildren(caja("aviso", `No pude pedir el trabajo: ${e.message}`));
        manual.disabled = false;
      }
    });
    actualizar();
    nodo.replaceChildren(
      el("h4", {}, "Elegir qué respuestas procesar"),
      el("p", { class: "nota-pie" }, lista.some((c) => c.fuera_de_plazo)
        ? "Las no marcadas quedan pendientes. Las que llegaron fuera de plazo vienen sin marcar."
        : "Las no marcadas quedan pendientes."),
      el("div", { class: "acciones" },
        el("button", { class: "enlace", type: "button", onclick: () => todas(true) }, "Todas"),
        el("button", { class: "enlace", type: "button", onclick: () => todas(false) }, "Ninguna")),
      ...lista.map((c, i) => el("details", { class: "candidato" },
        el("summary", {}, el("label", { class: "interruptor", onclick: (e) => e.stopPropagation() }, casillas[i],
          el("strong", {}, c.nombre)),
          el("span", { class: "tenue" }, [cuando(c.llegada), c.grupo, c.pregunta].filter(Boolean).join(" · ")),
          estadoCandidato(c) ? el("span", { class: "estado fallido" }, estadoCandidato(c)) : null,
          c.fuera_de_plazo ? el("span", { class: "estado fallido", title: "Respondió después del plazo del correo" },
            "fuera de plazo") : null),
        el("div", { class: "contenido respuesta" }, respuestaLegible(c.respuesta)))),
      el("div", { class: "acciones" }, boton, manual), aviso);
  }).catch(() => noPude("no hubo conexión o el archivo vino dañado"));
  return nodo;
}

/**
 * «con nota 6,0», «por revisar», «descartada» o "": si el candidato ya está
 * corregido. Los trabajos de antes de la revisión dejaban `ya_tiene_nota`.
 */
export function estadoCandidato(c) {
  if (c?.estado) return c.estado;
  return c?.ya_tiene_nota ? `ya tiene nota ${c.ya_tiene_nota}` : "";
}
