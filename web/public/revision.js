// Tests › Revisar: las correcciones que esperan al docente antes de que salga
// el feedback.
//
// Lee en el navegador log_envios.csv (la respuesta del alumno, su última
// corrección y si después hubo feedback o descarte), notas.csv (el estado),
// alumnos.csv (el nombre; el grupo no se muestra) y las decisiones de
// tests_semanales/revision/<id>.json, que escribe solo esta pestaña. El
// trabajo tests.feedback las lee y manda las que dicen `enviar`
// (modulos/tests/feedback.py).
//
// Las reglas que la página comparte con el trabajo (qué corrección es la
// vigente, si una decisión sigue valiendo, qué nota y qué texto salen) tienen
// su gemela en modulos/tests/decisiones.py, y pruebas/web.py compara las dos.

import {
  api, caja, conDetalle, confirmar, el, fechaCorta, idDe, pedirTrabajo, programadoPara, seguirTrabajo, urlTrabajos,
  vistaCorreo,
} from "./comun.js";
import { leerCsv } from "./csv.js";
import {
  aplicar, armarHtml, desdeDecision, pareceJson, leer as leerCorreccion, NOTA, ORIGINALIDADES, pideJson, quitarNumeros,
  valoresRubrica,
} from "./correccion.js";
import { leerConfiguracion } from "./configuracion.js";
import * as E from "./escala.js";
import { POR_DEFECTO } from "./escala.js";
import { asuntoDe, interruptorDeInstancia, leerSemana } from "./preguntas.js";

export const TESTS = "test";
export const APROBADA = "aprobada";
export const ENVIAR = "enviar";
export const DESCARTADA = "descartada";
const ESTADOS = [APROBADA, ENVIAR, DESCARTADA];
const DOCENTE = "docente:";
const DUPLICADO = "duplicado";

/** Dónde viven las decisiones de una instancia. El id solo aparece en rutas. */
export const rutaDecisiones = (id) => `tests_semanales/revision/${id}.json`;

// ---------------------------------------------------------------- lo que comparte con decisiones.py

/** Las filas de un CSV como objetos {columna: valor}. */
export function objetosCsv(texto) {
  if (!texto || !String(texto).trim()) return [];
  const { columnas, filas } = leerCsv(String(texto));
  return filas.map((f) => Object.fromEntries(columnas.map((c, i) => [c, f[i] ?? ""])));
}

/**
 * El texto de revision/<id>.json → { crudo, decisiones, ilegible }. `crudo` es
 * el objeto tal cual (se guarda sin perder entradas); `decisiones`, solo las
 * que el trabajo toma en cuenta (decisiones.leer), con el correo en minúsculas.
 */
export function leerDecisiones(texto) {
  if (texto === null || texto === undefined) return { crudo: {}, decisiones: {}, ilegible: false };
  let datos;
  try {
    datos = JSON.parse(String(texto).replace(/^﻿/, "") || "{}");
  } catch {
    return { crudo: {}, decisiones: {}, ilegible: true };
  }
  if (!datos || typeof datos !== "object" || Array.isArray(datos)) return { crudo: {}, decisiones: {}, ilegible: true };
  const decisiones = {};
  for (const [c, d] of Object.entries(datos)) {
    if (d && typeof d === "object" && ESTADOS.includes(d.estado)) decisiones[c.trim().toLowerCase()] = d;
  }
  return { crudo: datos, decisiones, ilegible: false };
}

export const esDelDocente = (c) => String(c?.Modelo || "").startsWith(DOCENTE);

/** `auto` o `revisar`: el modo con que se corrigió (Detalle `modo=…`). */
export function modoDe(c) {
  const m = String(c?.Detalle || "").match(/modo=(\w+)/);
  return m ? m[1] : "";
}

export const esDuplicado = (f) => f.Evento === "respuesta" && String(f.Detalle || "").trim() === DUPLICADO;

/**
 * Por alumno, su última `correccion` y si después hubo feedback o descarte
 * (decisiones.estado_por_correo). Agrega `cierre` (la fila que la cerró) y
 * `duplicados` (las respuestas que recibieron el correo de duplicado).
 * `filas` son las del log de una instancia, en orden.
 */
export function estadoPorCorreo(filas) {
  const salida = new Map();
  const nueva = () => ({ correccion: null, cerrada: false, cierre: null, respuesta: null, duplicados: [] });
  for (const fila of filas) {
    const correo = String(fila.Correo || "").trim().toLowerCase();
    const ev = fila.Evento;
    if (!correo) continue;
    if (ev === "correccion") {
      const previo = salida.get(correo) || nueva();
      salida.set(correo, { ...nueva(), correccion: fila, respuesta: previo.respuesta, duplicados: previo.duplicados });
    } else if ((ev === "evaluacion" || ev === "descarte") && salida.has(correo)) {
      Object.assign(salida.get(correo), { cerrada: true, cierre: fila });
    } else if (ev === "respuesta") {
      if (!salida.has(correo)) salida.set(correo, nueva());
      const e = salida.get(correo);
      // La primera respuesta no duplicada es la que se corrigió.
      if (esDuplicado(fila)) e.duplicados.push(fila);
      else if (!e.respuesta) e.respuesta = fila;
    }
  }
  return new Map([...salida].filter(([, e]) => e.correccion));
}

/** La `base` de una decisión: el Timestamp de la corrección sobre la que se decidió, tal cual. */
export const baseDe = (correccion) => String(correccion?.Timestamp || "");

// Como en Python, un objeto vacío cuenta como «no hay».
const hayAlgo = (o) => Boolean(o) && Object.keys(o).length > 0;

/** Si la decisión se tomó sobre esa corrección y no sobre una anterior (decisiones.vigente). */
export const vigente = (decision, correccion) => hayAlgo(decision) && hayAlgo(correccion)
  && String(decision.base || "") === baseDe(correccion);

const NOTA_FINAL = /(NOTA\s*FINAL\s*:?\s*(?:<\/?\w+[^>]*>\s*)*)([0-9]+(?:[.,][0-9]+)?)/i;

/** Pone `nota` en la línea NOTA FINAL del HTML (decisiones.reescribir_nota_final). */
export const reescribirNotaFinal = (html, nota) => String(html).replace(NOTA_FINAL, (_, antes) => antes + nota);

const vacio = (v) => v === undefined || v === null || v === "";

/** Si la corrección es del formato nuevo (JSON con puntajes), o la hizo el docente con puntajes (decisiones.es_formato_nuevo). */
export const esFormatoNuevo = (correccion, decision) => pareceJson(correccion?.EvaluacionIA)
  || (esDelDocente(correccion) && Array.isArray(decision?.puntajes));

/**
 * Lo que sale en el correo: la corrección con lo que el docente cambió encima
 * (decisiones.juntar, sin la originalidad). { nota, html, cambios, puntajes,
 * logro, problemas }. En el formato nuevo la nota sale de los puntajes con la
 * `escala` del semestre y el bloque muestra lo que diga `muestra`.
 */
export function juntar(correccion, decision, { escala = POR_DEFECTO, muestra = NOTA } = {}) {
  const d = decision || {};
  if (esFormatoNuevo(correccion, d)) {
    let c;
    let cambios = [];
    if (esDelDocente(correccion)) c = desdeDecision(d, (d.puntajes || []).length, escala);
    else ({ correccion: c, cambios } = aplicar(leerCorreccion(correccion?.EvaluacionIA, escala), d, escala));
    return { nota: c.nota, html: armarHtml(c, muestra, escala), cambios, puntajes: c.puntajes, logro: c.logro,
      problemas: c.problemas };
  }
  let html = correccion?.EvaluacionIA || "";
  let nota = String(correccion?.Nota || "").trim();
  const cambios = [];
  const htmlNuevo = d.html_legado;
  if (typeof htmlNuevo === "string" && htmlNuevo.trim() && htmlNuevo !== html) {
    html = htmlNuevo;
    cambios.push("texto");
  }
  if (!vacio(d.nota_legado)) {
    const notaNueva = String(d.nota_legado).trim().replaceAll(".", ",");
    if (notaNueva !== nota) {
      cambios.unshift(`nota ${nota || "—"} → ${notaNueva}`);
      nota = notaNueva;
    }
    html = reescribirNotaFinal(html, nota);
  }
  let logro = null;
  try { logro = nota ? E.logro(escala, nota) : null; } catch { logro = null; }
  return { nota, html: quitarNumeros(html, muestra), cambios, puntajes: "", logro: logro ? E.textoLogro(logro) : "",
    problemas: [] };
}

/** Qué le falta a una corrección hecha a mano para poder salir; "" si está completa (decisiones.faltante_manual). */
export function faltanteManual(decision, escala = POR_DEFECTO) {
  const d = decision || {};
  if (d.estado !== ENVIAR) return "falta que el docente la apruebe";
  if (Array.isArray(d.puntajes)) return desdeDecision(d, 0, escala).problemas.length ? "falta el puntaje de cada pregunta" : "";
  if (!/^\d{1,2}([.,]\d)?$/.test(String(d.nota_legado || "").trim())) return "falta la nota";
  if (!String(d.html_legado || "").trim()) return "falta el texto de la corrección";
  return "";
}

/** El HTML del modelo sin el ```html``` que a veces lo envuelve (evaluar._normalizar_html_gpt). */
export function normalizarHtml(html) {
  let h = String(html || "").trim();
  if (h.startsWith("```")) h = h.replace(/^```(?:html)?\s*/, "").replace(/\s*```$/, "");
  return h.trim();
}

/** El cuerpo del correo de corrección (feedback._construir_cuerpo_correccion). */
export function cuerpoCorreo(plantilla, html, nombre) {
  const evaluacion = normalizarHtml(html);
  if (!plantilla) return evaluacion;
  const corto = String(nombre || "").trim().split(/\s+/)[0] || "estudiante";
  // La corrección entra al final: si trajera "{NOMBRE}" escrito, no se toca.
  return plantilla.replaceAll("{NOMBRE}", () => corto).replaceAll("{EVALUACION}", () => evaluacion);
}

/** El aviso de ajuste cuando el semestre no tiene correo_ajuste.md (ajustar.AVISO_POR_DEFECTO). */
export const AVISO_POR_DEFECTO = "<p>Hola {NOMBRE}:</p>"
  + "<p>Revisamos otra vez tu corrección y tu nota quedó en {NOTA}.</p>"
  + "<p>Si tienes dudas, responde este correo.</p>";

/** El cuerpo del aviso de ajuste de nota (ajustar.cuerpo_aviso). */
export function cuerpoAviso(plantilla, nombre, nota, motivo = "") {
  const corto = String(nombre || "").trim().split(/\s+/)[0] || "estudiante";
  return String(plantilla ?? AVISO_POR_DEFECTO).replaceAll("{NOMBRE}", () => corto).replaceAll("{NOTA}", () => nota)
    .replaceAll("{MOTIVO}", () => motivo);
}

// ---------------------------------------------------------------- en qué está cada alumno

/**
 * Las correcciones de una instancia, cada una con su estado para la pestaña:
 *   por_revisar  sin decisión vigente (o con una sobre una corrección anterior: `vieja`)
 *   aprobada     lista, espera «Enviar las aprobadas»
 *   pedida       aprobada y con el envío pedido (decisión `enviar`)
 *   descarte     descartada en la página, todavía sin registrar
 *   enviada      el feedback salió (evaluacion en el log o Nota en notas.csv)
 *   descartada   el descarte quedó registrado
 */
export function casosDe(filasLog, filasNotas, decisiones, id) {
  const item = String(id);
  const notas = new Map(filasNotas.filter((f) => f.Flujo === TESTS && f.Item === item)
    .map((f) => [String(f.Correo || "").trim().toLowerCase(), f]));
  const lista = [];
  for (const [correo, e] of estadoPorCorreo(filasLog.filter((f) => f.Flujo === TESTS && f.Item === item))) {
    const fila = notas.get(correo) || {};
    const conNota = String(fila.Nota || "").trim();
    const descartada = String(fila.Descartada || "").trim();
    const d = decisiones[correo] || null;
    const vale = vigente(d, e.correccion);
    let estado;
    if (e.cerrada || conNota || descartada) {
      estado = e.cierre?.Evento === "descarte" || (descartada && !conNota) ? "descartada" : "enviada";
    } else if (d && vale) {
      estado = { [APROBADA]: "aprobada", [ENVIAR]: "pedida", [DESCARTADA]: "descarte" }[d.estado];
    } else {
      estado = "por_revisar";
    }
    const manual = esDelDocente(e.correccion);
    lista.push({
      correo, estado, correccion: e.correccion, decision: vale ? d : null,
      vieja: Boolean(d && !vale && estado === "por_revisar"),
      respuesta: e.respuesta, duplicados: e.duplicados, cierre: e.cierre, fila, manual,
      automatica: !manual && modoDe(e.correccion) === "auto",
    });
  }
  return lista;
}

/** Cuántas hay en cada filtro. */
export function conteos(casos) {
  const n = (...estados) => casos.filter((c) => estados.includes(c.estado)).length;
  return {
    porRevisar: n("por_revisar"), aprobadas: n("aprobada", "pedida"), enviadas: n("enviada"),
    descartadas: n("descarte", "descartada"), descartes: n("descarte"),
  };
}

const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

/** «Control 2 · 12 por revisar · 3 aprobadas»: una opción del selector. */
export function rotuloInstancia(nombre, c) {
  const partes = [nombre];
  if (c.porRevisar) partes.push(`${c.porRevisar} por revisar`);
  if (c.aprobadas) partes.push(plural(c.aprobadas, "aprobada", "aprobadas"));
  if (!c.porRevisar && !c.aprobadas) {
    if (c.descartes) partes.push(plural(c.descartes, "descarte sin registrar", "descartes sin registrar"));
    else if (c.enviadas) partes.push(plural(c.enviadas, "enviada", "enviadas"));
  }
  return partes.join(" · ");
}

/**
 * Las instancias para el selector, en orden de cierre: primero las que tienen
 * algo por revisar o aprobado (o un descarte sin registrar), después el resto
 * de las que tienen correcciones. [{ id, rotulo, cuenta, pendiente }]
 */
export function instanciasParaElegir(filasLog, filasNotas, decisionesPorId, { nombre, cierre }) {
  const ids = [...new Set(filasLog.filter((f) => f.Flujo === TESTS && f.Evento === "correccion")
    .map((f) => Number(f.Item)).filter((n) => Number.isInteger(n) && n >= 1))];
  const lista = ids.map((id) => {
    const cuenta = conteos(casosDe(filasLog, filasNotas, decisionesPorId.get(id) || {}, id));
    return { id, cuenta, rotulo: rotuloInstancia(nombre(id), cuenta),
      pendiente: Boolean(cuenta.porRevisar || cuenta.aprobadas || cuenta.descartes) };
  });
  const t = (id) => cierre(id)?.getTime?.() ?? Infinity;
  return lista.sort((a, b) => Number(b.pendiente) - Number(a.pendiente) || t(a.id) - t(b.id) || a.id - b.id);
}

/**
 * Las que «Aprobar todas» aprueba tal como las dejó la IA: las por revisar,
 * salvo las que en su tarjeta traen algo que mirar. Quedan para revisarlas una
 * por una las corregidas a mano (les falta lo del docente), las que no tienen
 * nota (un puntaje fuera de la rúbrica, o el HTML sin NOTA FINAL), las que
 * traen un aviso de la lectura (bloques que no calzan con las preguntas), las
 * de un alumno que respondió otra vez y las que la IA volvió a corregir
 * después de una decisión. `opciones` = { escala, muestra };
 * `nPreguntas(correo)`, cuántas preguntas tuvo ese alumno (o null).
 */
export function aprobablesEnBloque(casos, opciones = {}, nPreguntas = () => null) {
  return casos.filter((c) => {
    if (c.estado !== "por_revisar" || c.manual || c.vieja || c.duplicados?.length) return false;
    const j = juntar(c.correccion, null, opciones);
    if (j.problemas.length || String(j.nota || "").trim() === "") return false;
    return !leerCorreccion(c.correccion?.EvaluacionIA, opciones.escala || POR_DEFECTO, nPreguntas(c.correo))
      .avisos.length;
  });
}

/** La decisión que se guarda al aprobar: la nota y el HTML solo si el docente los cambió. */
export function decisionAl(estado, caso, { nota, html } = {}, ahora = new Date()) {
  const d = { estado, base: baseDe(caso.correccion) };
  const original = normalizarHtml(caso.correccion?.EvaluacionIA);
  const notaModelo = String(caso.correccion?.Nota || "").trim();
  const notaNueva = String(nota ?? "").trim().replaceAll(".", ",");
  if (caso.manual || (notaNueva && notaNueva !== notaModelo)) d.nota_legado = notaNueva;
  if (caso.manual || (html !== undefined && normalizarHtml(html) !== original)) d.html_legado = String(html ?? "");
  if (caso.manual) d.manual = true;
  d.cuando = ahora.toISOString();
  return d;
}

/**
 * La decisión que se guarda al aprobar una corrección del formato nuevo: los
 * puntajes, justificaciones, originalidad y retroalimentación solo si el
 * docente los cambió (en una corrección a mano, todo). `editado` es lo que hay
 * en el editor: { puntajes: [...], justificaciones: [...], originalidad, retroalimentacion }.
 */
export function decisionNueva(estado, caso, editado = {}, ahora = new Date(), escala = POR_DEFECTO) {
  const d = { estado, base: baseDe(caso.correccion) };
  const modelo = caso.manual ? null : leerCorreccion(caso.correccion?.EvaluacionIA, escala);
  const igual = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  if (Array.isArray(editado.puntajes)) {
    const puntajes = editado.puntajes.map((p) => (vacio(p) ? null : Number(String(p).replace(",", "."))));
    if (caso.manual || !igual(puntajes, modelo.preguntas.map((p) => Number(p.puntaje)))) d.puntajes = puntajes;
  }
  if (Array.isArray(editado.justificaciones)) {
    const js = editado.justificaciones.map((j) => String(j ?? "").trim());
    if (caso.manual || !igual(js, modelo.preguntas.map((p) => p.justificacion))) d.justificaciones = js;
  }
  for (const campo of ["originalidad", "retroalimentacion"]) {
    const v = String(editado[campo] ?? "").trim();
    if (v && (caso.manual || v !== modelo[campo])) d[campo] = v;
  }
  if (caso.manual) d.manual = true;
  d.cuando = ahora.toISOString();
  return d;
}

/** Una nota escrita a mano para esta escala: "" si está bien, o qué tiene (de min(1, mínima) a la máxima). */
export const problemaNota = (texto, escala = POR_DEFECTO) => E.problemaNota(escala, texto);

// ---------------------------------------------------------------- la pestaña

const urlArchivo = (semestre, ruta) => `/api/archivo/${encodeURIComponent(semestre)}/${ruta}`;

async function leerTexto(semestre, ruta) {
  const r = await fetch(urlArchivo(semestre, ruta), { cache: "no-store" });
  if (r.status === 404) return { texto: null, etag: null };
  if (!r.ok) throw new Error(`${ruta}: ${r.status} ${r.statusText}`);
  return { texto: await r.text(), etag: r.headers.get("etag") };
}

const NOMBRES_FILTRO = [
  ["por_revisar", "Por revisar"], ["aprobadas", "Aprobadas"], ["enviadas", "Enviadas"], ["descartadas", "Descartadas"],
];
const EN_FILTRO = {
  por_revisar: ["por_revisar"], aprobadas: ["aprobada", "pedida"], enviadas: ["enviada"],
  descartadas: ["descarte", "descartada"],
};

/** Un diálogo que pide el motivo del descarte. Devuelve el motivo, o null si se canceló. */
function pedirMotivo(nombre) {
  return new Promise((resolver) => {
    const motivo = el("textarea", { rows: "3", required: true, placeholder: "Por ejemplo: respondió otra pregunta." });
    const aceptar = el("button", { class: "primario peligro", type: "submit", value: "si" }, "Descartar");
    const dialogo = el("dialog", { class: "confirmar", "aria-label": "Descartar" },
      el("form", { method: "dialog" },
        el("p", { class: "texto-confirmar" }, `Vas a descartar la corrección de ${nombre}. No se le manda nada y `
          + "su casilla queda cerrada sin nota: después solo se le puede poner nota con un ajuste en Resultados.\n\n"
          + "El descarte se registra con el próximo envío; hasta entonces se puede volver a revisar."),
        el("label", { class: "campo-motivo" }, "Motivo (lo ve solo el equipo docente)", motivo),
        el("div", { class: "acciones" },
          el("button", { class: "secundario", type: "submit", value: "no", formnovalidate: true }, "Cancelar"), aceptar)));
    dialogo.addEventListener("close", () => {
      dialogo.remove();
      resolver(dialogo.returnValue === "si" && motivo.value.trim() ? motivo.value.trim() : null);
    });
    document.body.append(dialogo);
    dialogo.showModal();
    motivo.focus();
  });
}

/**
 * La pestaña Revisar. `ciclo` es el de ciclo.js (nombres y cierres); `id`, la
 * instancia con que abre (la de `#revisar/<id>`), o null para la primera con
 * algo pendiente. `alCambiarId(id)` deja el id en la URL; `alCambiar()` avisa
 * que cambió algo que cuenta el resto de la página; `alCambiarModo()`, que se
 * cambió el interruptor de revisión de una instancia.
 */
export function pestanaRevisar({ semestre, ciclo, id = null, alCambiarId = () => {}, alCambiar = () => {},
  alCambiarModo = () => {} }) {
  const nodo = el("div", { class: "revisar" }, el("p", { class: "cargando" }, "Leyendo las correcciones…"));
  const legado = ciclo?.legado !== false;
  const nombre = (n) => (ciclo ? ciclo.nombre(n) : `Semana ${n}`);
  const cierre = (n) => (ciclo ? ciclo.entregaDe(n).fecha : null);
  // El modo de cada instancia: el del ciclo, o el que se acaba de guardar acá.
  const modosGuardados = new Map();
  const modoDe = (n) => modosGuardados.get(n) ?? ciclo?.modoDe?.(n) ?? null;
  let filtro = "por_revisar";
  let datos = null;
  const resultado = el("div", { class: "resultado-revision" });

  async function cargar() {
    const [log, notas, alumnos, plantilla, archivos, escala, configuracion, prompt] = await Promise.all([
      leerTexto(semestre, "log_envios.csv"), leerTexto(semestre, "notas.csv"), leerTexto(semestre, "alumnos.csv"),
      leerTexto(semestre, "tests_semanales/prompts/correo_correccion.md"),
      api(`/api/archivos/${encodeURIComponent(semestre)}?prefijo=${encodeURIComponent("tests_semanales/revision/")}`),
      // La escala calcula la nota de los puntajes; correo_muestra dice qué números
      // ve el alumno; el prompt dice en qué formato corrige el docente a mano.
      leerTexto(semestre, E.ARCHIVO), leerTexto(semestre, "configuracion.json"),
      leerTexto(semestre, "tests_semanales/prompts/evaluar_respuesta.md"),
    ]);
    const decisionesPorId = new Map();
    const archivosPorId = new Map();
    await Promise.all(archivos.map(async (a) => {
      const m = a.ruta.match(/^tests_semanales\/revision\/(\d+)\.json$/);
      if (!m) return;
      const leido = await leerTexto(semestre, a.ruta);
      const d = leerDecisiones(leido.texto);
      decisionesPorId.set(Number(m[1]), d.decisiones);
      archivosPorId.set(Number(m[1]), { ...d, etag: leido.etag });
    }));
    const filasAlumnos = objetosCsv(alumnos.texto);
    const escalaLeida = E.leerEscala(escala.texto);
    datos = {
      log: objetosCsv(log.texto), notas: objetosCsv(notas.texto), plantilla: plantilla.texto,
      nombres: new Map(filasAlumnos.map((a) => [String(a.Correo || "").trim().toLowerCase(), a.Nombre || ""])),
      // El grupo no se muestra: solo dice cuántas preguntas tuvo cada alumno.
      grupos: new Map(filasAlumnos.map((a) => [String(a.Correo || "").trim().toLowerCase(),
        String(a.Grupo || "control").trim().toLowerCase()])),
      decisionesPorId, archivosPorId,
      escala: escalaLeida.escala, errorEscala: escalaLeida.error,
      muestra: leerConfiguracion(configuracion.texto).muestra,
      formatoNuevo: pideJson(prompt.texto),
    };
  }

  /** Cuántas preguntas no vacías tuvo el alumno en esa instancia (las de su grupo), o null si no se sabe. */
  function nPreguntasDe(correo, n) {
    const inst = ciclo?.preguntas ? leerSemana(ciclo.preguntas, n) : null;
    if (!inst?.preguntas) return null;
    const g = datos.grupos.get(correo) === "tratamiento" ? "tratamiento" : "control";
    return inst.preguntas.map((p) => (p.igual ? p.control : p[g])?.texto?.trim()).filter(Boolean).length || null;
  }

  const decisionesDe = (n) => datos.decisionesPorId.get(n) || {};

  /** Relee solo las decisiones de una instancia (tras un 409, o antes de pedir el envío). */
  async function releerDecisiones(n) {
    const leido = await leerTexto(semestre, rutaDecisiones(n));
    const d = leerDecisiones(leido.texto);
    datos.decisionesPorId.set(n, d.decisiones);
    datos.archivosPorId.set(n, leido.texto === null ? undefined : { ...d, etag: leido.etag });
  }

  /**
   * Guarda revision/<id>.json con lo que hace `cambiar(crudo)` sobre la versión
   * leída. Si alguien lo guardó entretanto (409), relee y aplica el mismo
   * cambio una vez más; el cambio es por alumno, así que no pisa a nadie.
   */
  async function guardar(n, cambiar, detalle) {
    for (let intento = 0; ; intento++) {
      const actual = datos.archivosPorId.get(n);
      if (actual?.ilegible) throw new Error(`${rutaDecisiones(n)} no se puede leer; hay que revisarlo a mano.`);
      const nuevo = cambiar(structuredClone(actual?.crudo || {}));
      const r = await fetch(urlArchivo(semestre, rutaDecisiones(n)), {
        method: "PUT", body: `${JSON.stringify(nuevo, null, 2)}\n`,
        headers: { "content-type": "application/json; charset=utf-8",
          ...(actual?.etag ? { "if-match": actual.etag } : { "if-none-match": "*" }), ...conDetalle(detalle) },
      });
      if (r.ok) {
        const { etag } = await r.json().catch(() => ({}));
        const d = leerDecisiones(JSON.stringify(nuevo));
        datos.decisionesPorId.set(n, d.decisiones);
        datos.archivosPorId.set(n, { ...d, etag: etag || null });
        if (!etag) await releerDecisiones(n);
        return;
      }
      if (r.status !== 409 || intento >= 1) {
        const cuerpo = await r.json().catch(() => ({}));
        throw new Error(cuerpo.error || `${r.status} ${r.statusText}`);
      }
      await releerDecisiones(n);
    }
  }

  /** La decisión de un correo en el JSON crudo (sin importar mayúsculas), o null. */
  const entradaDe = (crudo, correo) => {
    const k = Object.keys(crudo || {}).find((x) => x.trim().toLowerCase() === correo);
    return k === undefined ? null : crudo[k];
  };
  /** Cómo estaba la decisión de ese correo cuando el docente la vio, para comparar después. */
  const vistoDe = (n, correo) => JSON.stringify(entradaDe(datos.archivosPorId.get(n)?.crudo, correo));
  const AJENO = "Otra persona cambió esta corrección mientras la mirabas. Recarga la página para ver cómo quedó.";

  /**
   * Pone (o quita) la decisión de un correo. Con `visto`, solo si sigue como
   * la vio el docente: tras un 409 se relee, y si otra persona la descartó o
   * la editó entretanto, no se pisa (un descarte pisado saldría por correo).
   */
  const ponerDecision = (correo, decision, visto) => (crudo) => {
    if (visto !== undefined && JSON.stringify(entradaDe(crudo, correo)) !== visto) throw new Error(AJENO);
    // Un mismo correo puede venir con otras mayúsculas: queda una sola entrada.
    for (const k of Object.keys(crudo)) if (k.trim().toLowerCase() === correo) delete crudo[k];
    if (decision) crudo[correo] = decision;
    return crudo;
  };

  /** Pide el envío, o se suma a uno pedido que todavía no empieza (ese leerá las decisiones al partir). */
  async function pedirEnvio(n) {
    let pendiente = null;
    try {
      const pendientes = await api(urlTrabajos(semestre, "tests.", undefined, true));
      pendiente = pendientes.find((t) => t.flujo === "tests.feedback" && t.estado === "pendiente" && !t.prueba
        && !programadoPara(t) && Number(idDe(t.argumentos)) === n);
    } catch { /* sin la lista se pide uno nuevo */ }
    const trabajo = pendiente?.id
      || await pedirTrabajo(semestre, "tests.feedback", { [legado ? "semana" : "instancia"]: n, prueba: false });
    resultado.replaceChildren(...[pendiente ? caja("info", "Ya había un envío pedido que todavía no empezaba: lleva "
      + "también estas.") : null, el("div")].filter(Boolean));
    resultado.scrollIntoView({ behavior: "smooth", block: "start" });
    await seguirTrabajo(trabajo, resultado.lastChild, { alTerminar: () => recargar() });
  }

  let primera = true;
  async function recargar() {
    try {
      await cargar();
      dibujar();
      // Al abrir, el resto de la página ya está al día; después de un envío, no.
      if (!primera) alCambiar();
      primera = false;
    } catch (e) {
      nodo.replaceChildren(caja("aviso", `No pude leer las correcciones: ${e.message}`));
    }
  }

  // ---------------------------------------------------------------- una tarjeta

  /**
   * El editor de una corrección del formato viejo: la nota y el HTML completo.
   * { editor, borrador(), aprobada(estado, editado) → decisión | { falta } }.
   */
  function editorLegado(caso, previo, editable) {
    const base = juntar(caso.correccion, previo, opciones());
    const nota = el("input", { type: "text", inputmode: "decimal", size: "4",
      value: caso.manual && vacio(previo.nota_legado) ? "" : base.nota });
    const html = el("textarea", { class: "html-correccion", rows: "12", spellcheck: "false",
      placeholder: caso.manual ? "<p>La retroalimentación…</p>\n<p><strong>NOTA FINAL:</strong> 6,0</p>" : "" });
    html.value = caso.manual && vacio(previo.html_legado) ? "" : normalizarHtml(base.html);
    const editor = el("div", { class: "editor-correccion", hidden: !caso.manual || !editable },
      el("label", {}, "Nota", nota),
      el("label", {}, "El texto de la corrección (HTML)", html),
      el("p", { class: "nota-pie" }, caso.manual
        ? "La corriges tú: la nota y el texto son lo que recibe el alumno. Escribe «NOTA FINAL: 6,0» en el texto "
          + "si quieres que vea la nota."
        : "La nota reemplaza la de la línea «NOTA FINAL» del texto."));
    return {
      editor, base, campos: [nota, html],
      borrador: () => ({ nota_legado: nota.value, html_legado: html.value }),
      notaModelo: String(caso.correccion.Nota || "").trim(),
      aprobada: (estado, editado) => {
        const falta = editado || caso.manual ? problemaNota(nota.value, datos.escala) : "";
        if (falta || (caso.manual && !html.value.trim())) return { falta: falta || "Falta el texto de la corrección." };
        return decisionAl(estado, caso, editado ? { nota: nota.value, html: html.value }
          : { nota: previo.nota_legado, html: previo.html_legado });
      },
    };
  }

  /**
   * El editor de una corrección del formato nuevo: el puntaje y la
   * justificación de cada pregunta, la originalidad y la retroalimentación.
   * La nota no se escribe: la calcula la escala del semestre con los puntajes.
   */
  function editorNuevo(caso, previo, editable, nPreguntas) {
    const escala = datos.escala;
    const modelo = caso.manual ? null : leerCorreccion(caso.correccion.EvaluacionIA, escala, nPreguntas);
    const inicial = caso.manual ? desdeDecision(previo, nPreguntas || 1, escala) : aplicar(modelo, previo, escala).correccion;
    const valores = valoresRubrica(escala);
    const filas = inicial.preguntas.map((p) => {
      const puntaje = el("select", { "aria-label": `Puntaje de ${p.rotulo}` },
        el("option", { value: "" }, "—"),
        valores.map((v) => el("option", { value: v.valor, selected: String(p.puntaje) === v.valor }, v.texto)));
      const justificacion = el("textarea", { rows: "2", "aria-label": `Justificación de ${p.rotulo}` });
      justificacion.value = p.justificacion;
      return { p, puntaje, justificacion };
    });
    const actual = inicial.originalidad;
    const originalidad = el("select", { "aria-label": "Originalidad" },
      el("option", { value: "" }, "—"),
      [...new Set([...ORIGINALIDADES, ...(actual ? [actual] : [])])].map((o) =>
        el("option", { value: o, selected: o === actual }, o)));
    const retro = el("textarea", { rows: "4", "aria-label": "Retroalimentación" });
    retro.value = inicial.retroalimentacion;
    const leido = () => ({
      puntajes: filas.map((f) => (f.puntaje.value === "" ? null : f.puntaje.value)),
      justificaciones: filas.map((f) => f.justificacion.value),
      originalidad: originalidad.value, retroalimentacion: retro.value,
    });
    const editor = el("div", { class: "editor-correccion editor-puntajes", hidden: !caso.manual || !editable },
      filas.map((f) => el("fieldset", { class: "pregunta-revision" },
        el("legend", {}, f.p.rotulo),
        el("label", {}, `Puntaje (de 0 a ${valores.at(-1)?.texto ?? "3"})`, f.puntaje),
        el("label", {}, "Justificación", f.justificacion))),
      el("label", {}, "Originalidad", originalidad),
      el("label", {}, "Retroalimentación", retro),
      el("p", { class: "nota-pie" }, caso.manual
        ? "La corriges tú: pon el puntaje de cada pregunta y la nota sale de la escala del semestre."
        : "La nota se recalcula con la escala del semestre al cambiar un puntaje."));
    const decision = (estado) => decisionNueva(estado, caso, leido(), new Date(), escala);
    return {
      editor, base: juntar(caso.correccion, previo, opciones()),
      campos: [...filas.flatMap((f) => [f.puntaje, f.justificacion]), originalidad, retro],
      borrador: () => decision(previo.estado || APROBADA),
      notaModelo: caso.manual ? "" : modelo.nota,
      avisos: caso.manual ? [] : [...modelo.problemas, ...modelo.avisos],
      aprobada: (estado) => {
        const d = decision(estado);
        const j = juntar(caso.correccion, d, opciones());
        if (j.problemas.length) return { falta: caso.manual ? "Falta el puntaje de cada pregunta." : j.problemas.join(" ") };
        return d;
      },
    };
  }

  const opciones = () => ({ escala: datos.escala, muestra: datos.muestra });

  function tarjeta(n, caso, asunto) {
    const nombreAlumno = datos.nombres.get(caso.correo) || caso.correo;
    const llegada = caso.fila.Respondio || caso.respuesta?.Timestamp || "";
    const editable = ["por_revisar", "aprobada"].includes(caso.estado);
    // Un descarte guarda el motivo en `retroalimentacion`: no es una edición de la corrección.
    const previo = caso.decision && caso.decision.estado !== DESCARTADA ? caso.decision : {};
    const nuevo = caso.manual ? datos.formatoNuevo || Array.isArray(previo.puntajes)
      : esFormatoNuevo(caso.correccion, previo);
    const ed = nuevo ? editorNuevo(caso, previo, editable, nPreguntasDe(caso.correo, n))
      : editorLegado(caso, previo, editable);
    const { editor } = ed;
    const zonaCorreo = el("div", { class: "correo-propuesto" });
    const problema = el("p", { class: "aviso-correo", hidden: true });

    /** Lo que recibiría el alumno: lo enviado, o la corrección con lo editado encima. */
    const pintarCorreo = () => {
      let cuerpoHtml;
      let aviso;
      if (caso.estado === "enviada" && caso.cierre?.Evento === "evaluacion") {
        cuerpoHtml = caso.cierre.EvaluacionIA || "";
        aviso = `Se envió con nota ${caso.cierre.Nota || caso.fila.Nota || "?"}`
          + (caso.cierre.Detalle && caso.cierre.Detalle !== "auto" ? ` · ${caso.cierre.Detalle}` : " · automática");
      } else {
        const j = editable && !editor.hidden ? juntar(caso.correccion, ed.borrador(), opciones()) : ed.base;
        cuerpoHtml = j.html;
        const notaModelo = ed.notaModelo;
        aviso = caso.manual ? `Corrección a mano · nota ${j.nota || "sin escribir"}`
          : `Nota del modelo ${notaModelo || "?"}${j.nota !== notaModelo ? ` → ${j.nota || "sin nota"}` : ""}`;
        if (datos.muestra !== NOTA) aviso += ` · el alumno no ve ${datos.muestra === "nada" ? "ningún número" : "la nota"}`;
      }
      zonaCorreo.replaceChildren(vistaCorreo({
        asunto, para: caso.correo, nombre: nombreAlumno, html: true,
        cuerpo: cuerpoCorreo(datos.plantilla, cuerpoHtml, nombreAlumno),
      }, { aviso }));
    };
    let espera;
    const alEditar = () => {
      clearTimeout(espera);
      espera = setTimeout(pintarCorreo, 300);
      problema.hidden = true;
    };
    for (const campo of ed.campos) campo.addEventListener(campo.tagName === "SELECT" ? "change" : "input", alEditar);
    pintarCorreo();

    const avisos = [];
    if (editable) for (const a of ed.avisos || []) avisos.push(caja("aviso", a));
    if (caso.vieja) avisos.push(caja("aviso", "La IA volvió a corregir después de tu decisión: revisa otra vez."));
    if (caso.automatica && caso.estado === "por_revisar") {
      avisos.push(caja("info", "Se corrigió para salir sola, pero el feedback no salió. Ahora espera tu revisión."));
    }
    for (const dup of caso.duplicados) {
      avisos.push(el("details", { class: "aviso-duplicado" },
        el("summary", {}, `Respondió otra vez el ${fechaCorta(new Date(dup.Timestamp))}; recibió el correo de duplicado.`),
        el("div", { class: "respuesta-alumno" }, dup.Respuesta || "(sin texto)")));
    }
    if (caso.estado === "descarte" || caso.estado === "descartada") {
      const motivo = caso.estado === "descarte" ? caso.decision?.retroalimentacion : caso.cierre?.Detalle;
      avisos.push(caja("info", `Descartada${caso.estado === "descarte" ? " (se registra con el próximo envío)" : ""}: `
        + `${motivo || "sin motivo"}. El alumno no recibe nada.`));
    }
    if (caso.estado === "pedida") avisos.push(caja("info", "Aprobada y con el envío pedido."));

    // `alHacer` devuelve false si no hizo nada (faltaba algo, o se canceló):
    // el botón vuelve a quedar activo y lo editado sigue ahí.
    const accion = (texto, clase, alHacer) => el("button", { class: clase, type: "button", onclick: async (e) => {
      const boton = e.currentTarget;
      boton.disabled = true;
      try {
        if (await alHacer() === false) boton.disabled = false;
      } catch (err) {
        problema.textContent = `No pude guardarlo: ${err.message}`;
        problema.hidden = false;
        boton.disabled = false;
      }
    } }, texto);

    /**
     * La decisión con lo que está en el editor (o, cerrado, con lo que ya se
     * había editado); null si falta algo, y lo dice.
     */
    const aprobada = (estado) => {
      const d = ed.aprobada(estado, !editor.hidden);
      if (d.falta) {
        problema.textContent = d.falta;
        problema.hidden = false;
        editor.hidden = false;
        return null;
      }
      return d;
    };

    const botones = [];
    if (editable && !caso.manual) {
      botones.push(el("button", { class: "secundario", type: "button", onclick: () => {
        editor.hidden = !editor.hidden;
        pintarCorreo();
      } }, "Editar"));
    }
    // Lo que había al dibujar la tarjeta: si cambia antes de guardar, no se pisa.
    const visto = vistoDe(n, caso.correo);
    if (caso.estado === "por_revisar") {
      botones.push(accion("Aprobar", "primario", async () => {
        const d = aprobada(APROBADA);
        if (!d) return false;
        await guardar(n, ponerDecision(caso.correo, d, visto), `Aprobó la corrección de ${caso.correo} (${nombre(n)})`);
        dibujar();
      }));
    }
    if (editable) {
      botones.push(accion(caso.estado === "aprobada" ? "Enviar ahora" : "Aprobar y enviar", "primario real", async () => {
        const d = aprobada(ENVIAR);
        if (!d) return false;
        if (!await confirmar(`Vas a mandarle el feedback a ${nombreAlumno} (${nombre(n)}). Es un correo real y la nota `
          + "queda guardada.\n\n¿Confirmas?", "Enviar", "real")) return false;
        await guardar(n, ponerDecision(caso.correo, d, visto), `Aprobó y pidió enviar la corrección de ${caso.correo} (${nombre(n)})`);
        dibujar();
        await pedirEnvio(n);
      }));
      botones.push(accion("Descartar…", "secundario", async () => {
        const motivo = await pedirMotivo(nombreAlumno);
        if (!motivo) return false;
        await guardar(n, ponerDecision(caso.correo, {
          estado: DESCARTADA, base: baseDe(caso.correccion), retroalimentacion: motivo, cuando: new Date().toISOString(),
        }, visto), `Descartó la corrección de ${caso.correo} (${nombre(n)})`);
        dibujar();
      }));
    }
    if (["aprobada", "pedida", "descarte"].includes(caso.estado)) {
      const conCambios = caso.decision && ["html_legado", "nota_legado", "puntajes", "justificaciones", "originalidad"]
        .some((k) => caso.decision[k] !== undefined);
      botones.push(accion(conCambios && !caso.manual ? "Volver a lo de la IA" : "Volver a revisar", "secundario", async () => {
        await guardar(n, ponerDecision(caso.correo, null, visto), `Volvió a revisar la corrección de ${caso.correo} (${nombre(n)})`);
        dibujar();
      }));
    }

    return el("article", { class: `tarjeta tarjeta-revision ${caso.estado}` },
      el("header", {},
        el("h4", {}, nombreAlumno), el("span", { class: "tenue" }, caso.correo),
        el("span", { class: `estado ${caso.estado}` }, ETIQUETAS[caso.estado])),
      avisos,
      el("div", { class: "revision-columnas" },
        el("section", { class: "respuesta" },
          el("h5", {}, "Respuesta", llegada ? el("span", { class: "tenue" }, ` · llegó el ${fechaCorta(new Date(llegada))}`) : ""),
          el("div", { class: "respuesta-alumno" }, caso.respuesta?.Respuesta || "(no está en el log)")),
        el("section", { class: "correo" }, el("h5", {}, caso.estado === "enviada" ? "Lo que recibió" : "Lo que recibiría"),
          zonaCorreo, editable ? editor : null)),
      problema,
      botones.length ? el("div", { class: "acciones" }, botones) : null);
  }

  // ---------------------------------------------------------------- la lista

  function dibujar() {
    const opciones = instanciasParaElegir(datos.log, datos.notas, datos.decisionesPorId, { nombre, cierre });
    if (!opciones.length) {
      nodo.replaceChildren(el("p", {}, "Todavía no hay correcciones. Aparecen acá cuando se evalúan las respuestas de "
        + `${legado ? "una semana" : "una instancia"}.`), resultado);
      return;
    }
    if (!opciones.some((o) => o.id === id)) id = (opciones.find((o) => o.pendiente) || opciones[0]).id;
    alCambiarId(id);
    const selector = el("select", { "aria-label": legado ? "Semana" : "Instancia" },
      [["Con algo pendiente", opciones.filter((o) => o.pendiente)], ["Sin nada pendiente", opciones.filter((o) => !o.pendiente)]]
        .filter(([, l]) => l.length)
        .map(([titulo, l]) => el("optgroup", { label: titulo }, l.map((o) =>
          el("option", { value: String(o.id), selected: o.id === id }, o.rotulo)))));
    selector.addEventListener("change", () => { id = Number(selector.value); resultado.replaceChildren(); dibujar(); });

    const casos = casosDe(datos.log, datos.notas, decisionesDe(id), id);
    const cuenta = conteos(casos);
    const porFiltro = { por_revisar: cuenta.porRevisar, aprobadas: cuenta.aprobadas, enviadas: cuenta.enviadas,
      descartadas: cuenta.descartadas };
    const chips = el("div", { class: "chips", role: "group", "aria-label": "Filtro" }, NOMBRES_FILTRO.map(([k, t]) =>
      el("button", { class: "chip", type: "button", "aria-pressed": String(filtro === k), onclick: () => {
        filtro = k;
        dibujar();
      } }, `${t} (${porFiltro[k]})`)));
    const instancia = ciclo?.preguntas ? leerSemana(ciclo.preguntas, id) : null;
    const asunto = instancia ? `Re: ${asuntoDe(instancia)}` : "";
    const visibles = casos.filter((c) => EN_FILTRO[filtro].includes(c.estado))
      .sort((a, b) => (datos.nombres.get(a.correo) || a.correo).localeCompare(datos.nombres.get(b.correo) || b.correo, "es"));

    const ilegible = datos.archivosPorId.get(id)?.ilegible;
    // replaceChildren (a diferencia de el()) escribe un null como el texto "null": se filtra.
    nodo.replaceChildren(...[
      el("div", { class: "form-trabajo" }, el("label", {}, legado ? "Semana" : "Instancia", selector)),
      zonaModo(id, casos),
      ilegible ? caja("aviso", `${rutaDecisiones(id)} no se puede leer: no guardo nada encima. Hay que `
        + "revisarlo a mano.") : null,
      chips,
      filtro === "por_revisar" && cuenta.porRevisar && !ilegible ? ayudaAprobar(id, casos) : null,
      visibles.length ? visibles.map((c) => tarjeta(id, c, asunto))
        : el("p", { class: "tenue" }, filtro === "por_revisar" ? "No queda nada por revisar acá." : "Ninguna."),
      barraEnvio(id, casos),
      resultado].flat().filter(Boolean));
  }

  /**
   * El interruptor «Revisar las correcciones antes de enviarlas» de la
   * instancia elegida (solo en el formato nuevo). Se guarda apenas se aprieta;
   * pasar a automático dice cuántas quedan esperando acá, que no salen solas.
   */
  function zonaModo(n, casos) {
    if (legado || !ciclo?.preguntas || !leerSemana(ciclo.preguntas, n)) return null;
    const mensaje = el("div");
    const cuenta = conteos(casos);
    return el("div", { class: "zona-modo" }, interruptorDeInstancia({
      semestre, numero: n, nombre: nombre(n), modo: modoDe(n), mensaje,
      esperando: cuenta.porRevisar + cuenta.aprobadas,
      alGuardar: (modo) => { modosGuardados.set(n, modo); alCambiarModo(); },
    }), mensaje);
  }

  /** Qué hace cada botón, y «Aprobar todas» para las que quedan por revisar. */
  function ayudaAprobar(n, casos) {
    const enBloque = aprobablesEnBloque(casos, opciones(), (correo) => nPreguntasDe(correo, n));
    const fuera = casos.filter((c) => c.estado === "por_revisar").length - enBloque.length;
    const estado = el("span", { class: "estado-guardado" });
    const boton = enBloque.length ? el("button", { class: "secundario", type: "button", onclick: async () => {
      if (!await confirmar(`Vas a aprobar ${enBloque.length === 1 ? "la corrección que queda" : `las ${enBloque.length} `
        + "correcciones que quedan"} por revisar de ${nombre(n)}, tal como las dejó la IA. Todavía no sale nada: `
        + "después, «Enviar las aprobadas» les manda el feedback."
        + (fuera ? `\n\n${plural(fuera, "corrección queda", "correcciones quedan")} para revisar una por una: `
          + "las corregidas a mano, las que no tienen nota y las que traen un aviso." : "")
        + "\n\n¿Aprobarlas?", "Aprobar todas")) return;
      boton.disabled = true;
      estado.textContent = "Guardando…";
      try {
        const ahora = new Date();
        // Si tras un 409 otra persona ya decidió alguna, esa queda como la dejó.
        const vistas = new Map(enBloque.map((c) => [c.correo, vistoDe(n, c.correo)]));
        let saltadas = 0;
        await guardar(n, (crudo) => {
          saltadas = 0;
          for (const c of enBloque) {
            if (JSON.stringify(entradaDe(crudo, c.correo)) !== vistas.get(c.correo)) saltadas++;
            else ponerDecision(c.correo, decisionAl(APROBADA, c, {}, ahora))(crudo);
          }
          return crudo;
        }, `Aprobó ${plural(enBloque.length, "corrección", "correcciones")} de una vez (${nombre(n)})`);
        dibujar();
        if (saltadas) {
          resultado.replaceChildren(caja("aviso", `${plural(saltadas, "corrección", "correcciones")} no se `
            + "aprobaron: otra persona las cambió mientras tanto y quedaron como las dejó. Revísalas en la lista."));
        }
      } catch (e) {
        estado.textContent = `No pude guardarlas: ${e.message}`;
        boton.disabled = false;
      }
    } }, `Aprobar todas (${enBloque.length})`) : null;
    return el("div", { class: "ayuda-aprobar" },
      el("p", { class: "nota-pie" }, "«Aprobar» deja la corrección lista; las aprobadas salen juntas con «Enviar las "
        + "aprobadas». «Aprobar y enviar» la manda ahora."),
      boton ? el("div", { class: "acciones" }, boton, estado) : null);
  }

  /** «Enviar las 23 aprobadas»: pasa las aprobadas a `enviar` en un guardado y pide un trabajo. */
  function barraEnvio(n, casos) {
    const aprobadas = casos.filter((c) => c.estado === "aprobada" || c.estado === "pedida");
    const descartes = casos.filter((c) => c.estado === "descarte");
    if (!aprobadas.length && !descartes.length) return null;
    const texto = aprobadas.length
      ? `Enviar ${aprobadas.length === 1 ? "la aprobada" : `las ${aprobadas.length} aprobadas`}`
        + (descartes.length ? ` y registrar ${plural(descartes.length, "descarte", "descartes")}` : "")
      : `Registrar ${plural(descartes.length, "descarte", "descartes")}`;
    const boton = el("button", { class: "primario real", type: "button" }, texto);
    const estado = el("span", { class: "estado-guardado" });
    boton.addEventListener("click", async () => {
      const partes = [];
      if (aprobadas.length) {
        partes.push(`Sale el feedback a ${plural(aprobadas.length, "alumno", "alumnos")} de ${nombre(n)}. Son correos `
          + "reales y la nota de cada uno queda guardada.");
      }
      if (descartes.length) {
        partes.push(`${plural(descartes.length, "corrección queda descartada", "correcciones quedan descartadas")}: `
          + "no reciben nada y su casilla se cierra sin nota.");
      }
      if (!await confirmar(`${partes.join("\n\n")}\n\n¿Confirmas?`, texto, "real")) return;
      boton.disabled = true;
      estado.textContent = "Guardando…";
      try {
        const correos = new Set(casos.filter((c) => c.estado === "aprobada").map((c) => c.correo));
        if (correos.size) {
          await guardar(n, (crudo) => {
            for (const [k, d] of Object.entries(crudo)) {
              if (correos.has(k.trim().toLowerCase()) && d?.estado === APROBADA) d.estado = ENVIAR;
            }
            return crudo;
          }, `Pidió enviar ${plural(correos.size, "corrección aprobada", "correcciones aprobadas")} (${nombre(n)})`);
        }
        dibujar();
        await pedirEnvio(n);
      } catch (e) {
        estado.textContent = `No pude pedir el envío: ${e.message}`;
        boton.disabled = false;
      }
    });
    return el("div", { class: "barra-guardar" }, estado, el("span", { class: "espacio" }), boton);
  }

  recargar();
  return nodo;
}

const ETIQUETAS = {
  por_revisar: "por revisar", aprobada: "aprobada", pedida: "envío pedido", descarte: "descartada",
  enviada: "enviada", descartada: "descartada",
};
