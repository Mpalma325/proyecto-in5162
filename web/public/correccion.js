// La corrección de un test en la página: la gemela de modulos/tests/correccion.py.
//
// Lee la corrección del modelo (JSON nuevo o HTML viejo), valida los puntajes
// contra la rúbrica, calcula logro y nota con la escala del semestre y arma el
// bloque del correo según correo_muestra (nota, puntajes o nada). La pestaña
// Revisar la usa para la vista previa y para recalcular la nota cuando el
// docente cambia un puntaje. pruebas/correccion.py compara las dos.
//
// Sin dependencias de la página (solo escala.js), para probarla en Node.

import * as E from "./escala.js";

export const JSON_ = "json";
export const HTML = "html";
export const NOTA = "nota";
export const PUNTAJES = "puntajes";
export const NADA = "nada";
export const MUESTRAS = [NOTA, PUNTAJES, NADA];

// ---------------------------------------------------------------- formato viejo

/** El HTML del modelo sin el ```html``` que a veces lo envuelve (_normalizar_html_gpt). */
export function normalizarHtml(html) {
  let h = String(html || "").trim();
  if (h.startsWith("```")) h = h.replace(/^```(?:html)?\s*/, "").replace(/\s*```$/, "");
  return h.trim();
}

const LINEA_TOTALES = /(?:<(?:b|strong)>\s*)?(?:NOTA\s*FINAL|PUNTAJE\s*TOTAL)\s*:?\s*(?:<\/(?:b|strong)>)?[^<\n]*(?:<br\s*\/?>)?\n?/gi;
const LINEA_EVALUACION = /(?:<(?:b|strong)>\s*)?EVALUACI[OÓ]N\s*:\s*(?:<\/(?:b|strong)>)?[^<\n]*(?:<br\s*\/?>)?\n?/gi;
const PARRAFO_VACIO = /<p>\s*(?:<br\s*\/?>\s*)*<\/p>\n?/gi;

/** El HTML viejo sin los números que el semestre no muestra (correccion.quitar_numeros). */
export function quitarNumeros(html, muestra) {
  if (![PUNTAJES, NADA].includes(muestra)) return html;
  let salida = String(html).replace(LINEA_TOTALES, "");
  if (muestra === NADA) salida = salida.replace(LINEA_EVALUACION, "");
  salida = salida.replace(/<br\s*\/?>\s*<\/p>/gi, "</p>");
  return salida.replace(PARRAFO_VACIO, "");
}

/** La nota de la línea NOTA FINAL de un HTML viejo, con coma; "" si no la tiene. */
export function notaDeHtml(html) {
  const texto = normalizarHtml(html).replace(/<[^>]*>/g, "\n");
  const m = texto.match(/NOTA\s*FINAL\s*:?\s*([0-9]+(?:[.,][0-9]+)?)/i);
  return m ? m[1].replaceAll(".", ",") : "";
}

/**
 * La originalidad de la línea «ORIGINALIDAD:» de un HTML viejo; "" si no la
 * tiene. Como extraer_nota_y_originalidad: la línea tiene que empezar con la
 * etiqueta, para no tomar una mención de la palabra en la retroalimentación.
 */
export function originalidadDeHtml(html) {
  const texto = normalizarHtml(html).replace(/<[^>]*>/g, "\n");
  const m = texto.match(/^\s*ORIGINALIDAD\s*:\s*([^\n]+)/im);
  if (!m) return "";
  let valor = m[1].trim();
  for (const sep of [".", "\n", "|", "<"]) if (valor.includes(sep)) valor = valor.split(sep)[0].trim();
  return valor;
}

// ---------------------------------------------------------------- formato nuevo

/** El objeto de una corrección del formato nuevo, o null si no lo es (correccion.datos_json). */
export function datosJson(texto) {
  let t = String(texto ?? "").trim();
  if (t.startsWith("```")) t = t.replace(/^```(?:json)?\s*/, "").replace(/\s*```$/, "");
  if (!t.startsWith("{")) return null;
  let datos;
  try { datos = JSON.parse(t); } catch { return null; }
  return datos && typeof datos === "object" && !Array.isArray(datos) && Array.isArray(datos.preguntas) ? datos : null;
}

/** 2 → "2"; 1/2 → "0.5": como se guardan los puntajes en el log. */
const punto = (f) => (f.d === 1n ? String(f.n) : String(E.aNumero(f)));
const coma = (f) => punto(f).replace(".", ",");

/** Los puntajes que puede tener una pregunta: 0; 0,5; y los enteros hasta el máximo. */
export function rubrica(escala) {
  const maximo = E.fraccion(escala.puntaje_maximo_pregunta);
  const tope = Number(maximo.d === 1n ? maximo.n : maximo.n / maximo.d);
  const valores = [E.fr(0n), E.fr(1n, 2n)];
  for (let i = 1; i <= tope; i++) valores.push(E.fr(BigInt(i)));
  if (!valores.some((v) => E.igual(v, maximo))) valores.push(maximo);
  return valores.filter((v) => E.comparar(v, maximo) <= 0);
}

export const textoRubrica = (escala) => rubrica(escala).map(coma).join("; ");

/** Las opciones de puntaje para un selector: [{ valor: "0.5", texto: "0,5" }, …]. */
export const valoresRubrica = (escala) => rubrica(escala).map((f) => ({ valor: punto(f), texto: coma(f) }));

/** Los niveles de originalidad que pide el prompt, de menor a mayor. */
export const ORIGINALIDADES = ["Muy Baja", "Baja", "Media", "Alta", "Muy Alta"];

const NUMERO = /^\d+(?:[.,]\d+)?$/;

/** El puntaje como fracción, o null si no es uno de la rúbrica (correccion.leer_puntaje). */
export function leerPuntaje(valor, escala) {
  if (typeof valor === "number") {
    if (!Number.isFinite(valor)) return null;
  } else if (typeof valor !== "string") {
    return null;
  }
  const texto = typeof valor === "string" ? valor.trim() : String(valor);
  if (!NUMERO.test(texto)) return null;
  const f = E.fraccion(texto);
  return rubrica(escala).some((v) => E.igual(v, f)) ? f : null;
}

/** Cómo se muestra un puntaje que no se entiende, en el aviso. */
function textoValor(valor) {
  if (typeof valor === "string") return valor.trim() || "vacío";
  if (valor === null || valor === undefined) return "vacío";
  if (typeof valor === "boolean") return valor ? "true" : "false";
  return String(valor);
}

const textoDe = (v) => (typeof v === "string" ? v.trim() : "");
const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;
const escalar = (v) => (typeof v === "number" || typeof v === "string") ? v : "";

/**
 * La corrección del modelo como objeto, con la nota calculada (correccion.leer).
 * { formato, preguntas, originalidad, justificacion_originalidad,
 *   retroalimentacion, html, puntajes, logro, nota, problemas, avisos }
 */
export function leer(texto, escala = E.POR_DEFECTO, nPreguntas = null) {
  const datos = datosJson(texto);
  if (!datos) {
    const crudo = String(texto ?? "");
    const nota = crudo.trim() ? notaDeHtml(crudo) : "";
    let l = null;
    try { l = nota ? E.logro(escala, nota) : null; } catch { l = null; }
    return {
      formato: HTML, preguntas: [], originalidad: crudo.trim() ? originalidadDeHtml(crudo) : "",
      justificacion_originalidad: "", retroalimentacion: "",
      html: crudo, puntajes: "", logro: l ? E.textoLogro(l) : "", nota, problemas: [], avisos: [],
    };
  }
  const preguntas = (datos.preguntas || []).map((p, i) => {
    const q = p && typeof p === "object" && !Array.isArray(p) ? p : {};
    return {
      rotulo: textoDe(q.rotulo) || `P${i + 1}`, respuesta: textoDe(q.respuesta),
      puntaje: escalar(q.puntaje), justificacion: textoDe(q.justificacion),
    };
  });
  return calcular({
    formato: JSON_, preguntas, originalidad: textoDe(datos.originalidad),
    justificacion_originalidad: textoDe(datos.justificacion_originalidad),
    retroalimentacion: textoDe(datos.retroalimentacion),
    html: "", puntajes: "", logro: "", nota: "", problemas: [], avisos: [],
  }, escala, nPreguntas);
}

/** Valida los puntajes de una corrección nueva y calcula logro y nota (correccion.calcular). */
export function calcular(c0, escala = E.POR_DEFECTO, nPreguntas = null) {
  const c = { ...c0, preguntas: c0.preguntas.map((p) => ({ ...p })), problemas: [], avisos: [] };
  if (c.formato !== JSON_) return c;
  const puntajes = [];
  for (const p of c.preguntas) {
    const f = leerPuntaje(p.puntaje, escala);
    if (!f) {
      c.problemas.push(`${p.rotulo}: el puntaje «${textoValor(p.puntaje)}» no está en la rúbrica (${textoRubrica(escala)}).`);
    } else {
      p.puntaje = punto(f);
    }
    puntajes.push(f);
  }
  if (!c.preguntas.length) c.problemas.push("La corrección no trae preguntas.");
  const n = c.preguntas.length;
  if (nPreguntas && n && n !== nPreguntas) {
    if (n < nPreguntas) {
      c.avisos.push(`La IA devolvió ${plural(n, "bloque", "bloques")} para ${nPreguntas} preguntas: puede haber juntado `
        + `preguntas. La nota se calculó sobre ${plural(n, "bloque", "bloques")}.`);
    } else {
      c.avisos.push(`La IA devolvió ${n} bloques para ${plural(nPreguntas, "pregunta", "preguntas")}.`);
    }
  }
  if (c.problemas.length) return Object.assign(c, { puntajes: "", logro: "", nota: "" });
  const l = E.logroDe(escala, puntajes);
  return Object.assign(c, { puntajes: puntajes.map(punto).join(";"), logro: E.textoLogro(l), nota: E.nota(escala, l) });
}

// ---------------------------------------------------------------- decisiones del docente

/** La corrección nueva con lo que el docente cambió en Revisar, y la lista de cambios (correccion.aplicar). */
export function aplicar(c, decision, escala = E.POR_DEFECTO) {
  const d = decision || {};
  let nueva = { ...c, preguntas: c.preguntas.map((p) => ({ ...p })) };
  const cambios = [];
  const antes = c.preguntas.map((p) => textoValor(p.puntaje)).join(";");
  if (Array.isArray(d.puntajes)) {
    nueva.preguntas.forEach((p, i) => {
      const v = d.puntajes[i];
      if (i < d.puntajes.length && v !== null && v !== undefined && v !== "") p.puntaje = v;
    });
  }
  if (Array.isArray(d.justificaciones)) {
    const pares = nueva.preguntas.slice(0, d.justificaciones.length).map((p, i) => [p, d.justificaciones[i]]);
    if (pares.some(([p, j]) => typeof j === "string" && j.trim() !== p.justificacion)) cambios.push("justificaciones");
    for (const [p, j] of pares) if (typeof j === "string") p.justificacion = j.trim();
  }
  for (const [campo, nombre] of [["originalidad", "originalidad"], ["retroalimentacion", "retroalimentación"]]) {
    const v = d[campo];
    if (typeof v === "string" && v.trim() && v.trim() !== (c[campo] || "")) {
      cambios.push(campo === "originalidad" ? `originalidad ${c[campo] || "—"} → ${v.trim()}` : nombre);
      nueva[campo] = v.trim();
    }
  }
  nueva = calcular(nueva, escala);
  const despues = nueva.preguntas.map((p) => textoValor(p.puntaje)).join(";");
  if (despues !== antes) cambios.unshift(`puntajes ${antes} → ${despues}`);
  return { correccion: nueva, cambios };
}

/** La corrección que escribe el docente a mano en el formato nuevo (correccion.desde_decision). */
export function desdeDecision(decision, nPreguntas, escala = E.POR_DEFECTO) {
  const d = decision || {};
  const puntajes = Array.isArray(d.puntajes) ? d.puntajes : [];
  const justificaciones = Array.isArray(d.justificaciones) ? d.justificaciones : [];
  const n = Math.max(puntajes.length, nPreguntas || 0);
  const preguntas = Array.from({ length: n }, (_, i) => ({
    rotulo: `P${i + 1}`, respuesta: "",
    puntaje: i < puntajes.length && puntajes[i] !== null && puntajes[i] !== undefined ? puntajes[i] : "",
    justificacion: i < justificaciones.length ? textoDe(justificaciones[i]) : "",
  }));
  return calcular({
    formato: JSON_, preguntas, originalidad: textoDe(d.originalidad), justificacion_originalidad: "",
    retroalimentacion: textoDe(d.retroalimentacion), html: "", puntajes: "", logro: "", nota: "", problemas: [], avisos: [],
  }, escala);
}

// ---------------------------------------------------------------- armado

/** Como `escapar` de comun.js: &, <, > y comillas dobles. */
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const conSaltos = (t) => String(t).replaceAll("\r\n", "\n").split("\n").map(esc).join("<br>\n");
const rotulo = (p) => (p.rotulo.endsWith(".") ? p.rotulo : `${p.rotulo}.`);
const puntajeComa = (v) => { const t = textoValor(v); return NUMERO.test(t) ? t.replaceAll(".", ",") : t; };
const maximo = (escala) => coma(E.fraccion(escala.puntaje_maximo_pregunta));

function total(c, escala) {
  const s = c.puntajes.split(";").map(E.fraccion).reduce(E.suma, E.fr(0n));
  const m = E.por(E.fraccion(escala.puntaje_maximo_pregunta), E.fr(BigInt(c.preguntas.length)));
  return `${coma(s)} de ${coma(m)} puntos`;
}

/** El bloque que va en {EVALUACION} del correo (correccion.armar_html). */
export function armarHtml(c, muestra = NOTA, escala = E.POR_DEFECTO) {
  if (c.formato !== JSON_) return muestra === NOTA ? c.html : quitarNumeros(c.html, muestra);
  const varias = c.preguntas.length > 1;
  const partes = ["<p><strong>EVALUACIÓN SEGÚN PAUTA</strong></p>"];
  for (const p of c.preguntas) {
    const lineas = varias ? [`<u>${esc(rotulo(p))}</u>`] : [];
    if (p.respuesta) lineas.push(`<b>RESPUESTA:</b> ${conSaltos(p.respuesta)}`);
    if (muestra !== NADA) lineas.push(`<b>EVALUACIÓN:</b> ${puntajeComa(p.puntaje)} / ${maximo(escala)} puntos`);
    if (p.justificacion) lineas.push(`<b>JUSTIFICACIÓN:</b> ${conSaltos(p.justificacion)}`);
    if (lineas.length) partes.push(`<p>${lineas.join("<br>\n")}</p>`);
  }
  partes.push("<hr>");
  if (muestra === NOTA && c.nota) {
    const lineas = varias ? [`<b>PUNTAJE TOTAL:</b> ${total(c, escala)}`] : [];
    lineas.push(`<b>NOTA FINAL:</b> ${c.nota}`);
    partes.push(`<p>${lineas.join("<br>\n")}</p>`);
  }
  if (c.originalidad) partes.push(`<p><b>ORIGINALIDAD:</b> ${esc(c.originalidad)}</p>`);
  if (c.justificacion_originalidad) {
    partes.push(`<p><b>JUSTIFICACIÓN ORIGINALIDAD:</b> ${conSaltos(c.justificacion_originalidad)}</p>`);
  }
  if (c.retroalimentacion) partes.push(`<p><b>RETROALIMENTACIÓN:</b><br>\n${conSaltos(c.retroalimentacion)}</p>`);
  return partes.join("\n");
}

/** La corrección para el equipo docente, siempre con puntajes y NOTA FINAL (correccion.texto_docente). */
export function textoDocente(c, escala = E.POR_DEFECTO) {
  if (c.formato !== JSON_) return normalizarHtml(c.html);
  const lineas = ["EVALUACIÓN SEGÚN PAUTA"];
  for (const p of c.preguntas) {
    lineas.push("", rotulo(p));
    if (p.respuesta) lineas.push(`RESPUESTA: ${p.respuesta}`);
    lineas.push(`EVALUACIÓN: ${puntajeComa(p.puntaje)} / ${maximo(escala)} puntos`);
    if (p.justificacion) lineas.push(`JUSTIFICACIÓN: ${p.justificacion}`);
  }
  lineas.push("");
  if (c.nota && c.preguntas.length > 1) lineas.push(`PUNTAJE TOTAL: ${total(c, escala)}`);
  lineas.push(`NOTA FINAL: ${c.nota || "sin nota"}`);
  if (c.originalidad) lineas.push(`ORIGINALIDAD: ${c.originalidad}`);
  if (c.justificacion_originalidad) lineas.push(`JUSTIFICACIÓN ORIGINALIDAD: ${c.justificacion_originalidad}`);
  if (c.retroalimentacion) lineas.push(`RETROALIMENTACIÓN: ${c.retroalimentacion}`);
  for (const a of [...c.problemas, ...c.avisos]) lineas.push(`AVISO: ${a}`);
  return lineas.join("\n");
}

/** Si el prompt de corrección pide la salida en JSON con «"puntaje"» (correccion.pide_json). */
export const pideJson = (prompt) => /\bJSON\b/.test(String(prompt || "")) && String(prompt || "").includes('"puntaje"');
