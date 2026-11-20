// La configuración del semestre: configuracion.json, en su raíz.
//
//   {"revision": "revisar", "correo_muestra": "nota"}
//
// La misma lectura que modulos/semestre/configuracion.py: sin archivo rige lo
// de antes (automático); un archivo que no se entiende cuenta como revisión,
// para que ante la duda nada salga sin que el docente lo vea. La escribe solo
// Configuración › Semestre; los trabajos la leen al correr.
//
// El modo de revisión se elige en cada instancia (columna Revision de
// preguntas.csv, modoInstancia). El de configuracion.json queda de respaldo
// para las filas que no dicen el suyo.

export const RUTA_CONFIGURACION = "configuracion.json";
export const AUTO = "auto";
export const REVISAR = "revisar";
export const MUESTRAS = ["nota", "puntajes", "nada"];

/**
 * El texto del archivo (o null si no existe) → { existe, modo, muestra, datos }.
 * `modo` es el de respaldo del semestre. `datos` es el objeto tal cual, para
 * guardarlo sin perder claves que la página no conoce (también `revision`,
 * que la página ya no cambia); null si el archivo no se pudo leer.
 */
export function leerConfiguracion(texto) {
  if (texto === null || texto === undefined) return { existe: false, modo: AUTO, muestra: "nota", datos: null };
  let datos;
  try {
    datos = JSON.parse(String(texto).replace(/^﻿/, "") || "{}");
  } catch {
    return { existe: true, modo: REVISAR, muestra: "nota", datos: null, ilegible: true };
  }
  if (!datos || typeof datos !== "object" || Array.isArray(datos)) {
    return { existe: true, modo: REVISAR, muestra: "nota", datos: null, ilegible: true };
  }
  // Con archivo pero sin la clave: revisión, igual que en Python.
  const valor = String(datos.revision || REVISAR).trim().toLowerCase();
  const modo = [AUTO, REVISAR].includes(valor) ? valor : REVISAR;
  const muestra = String(datos.correo_muestra || "nota").trim().toLowerCase();
  return { existe: true, modo, muestra: MUESTRAS.includes(muestra) ? muestra : "nota", datos };
}

/**
 * El modo de una instancia a partir de su columna Revision: `auto` o
 * `revisar` (sin importar mayúsculas ni espacios); vacía, `respaldo` (el de
 * configuracion.json; sin archivo, automático). Un valor que no se entiende
 * cuenta como revisión. Gemela de configuracion.modo_instancia (Python).
 */
export function modoInstancia(valor, respaldo) {
  const texto = String(valor || "").split(/\s+/).filter(Boolean).join(" ").toLowerCase();
  if (!texto) return respaldo;
  return [AUTO, REVISAR].includes(texto) ? texto : REVISAR;
}

/** Lee configuracion.json del semestre, con su etag para guardarlo. Sin archivo: { existe: false, … }. */
export async function cargarConfiguracion(semestre) {
  const r = await fetch(`/api/archivo/${encodeURIComponent(semestre)}/${RUTA_CONFIGURACION}`, { cache: "no-store" });
  if (r.status === 404) return { ...leerConfiguracion(null), etag: null };
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return { ...leerConfiguracion(await r.text()), etag: r.headers.get("etag") };
}

/** Lo que pasa con una corrección según el modo, dicho para el docente. */
export const describirModo = (modo) => (modo === AUTO
  ? "cada corrección se le manda al alumno apenas queda lista"
  : "las correcciones esperan en Tests › Revisar y el alumno no recibe nada hasta que se aprueban");

// ---------------------------------------------------------------- el interruptor de cada instancia

/** El rótulo del interruptor: encendido es revisar, apagado es automático. */
export const ROTULO_REVISION = "Revisar las correcciones antes de enviarlas";

/** Lo que pasa en cada posición del interruptor, en una línea. */
export const AYUDA_REVISION = "Encendido: cada corrección espera en Tests › Revisar hasta que la apruebes. "
  + "Apagado: el alumno la recibe por correo apenas queda lista.";
