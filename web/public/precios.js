// «Traer precios», en Configuración › Parámetros: qué hacer con cada fila de
// la tabla de precios según lo que sugiere el sitio (/api/precios-sugeridos,
// src/precios.ts). Sin DOM, para probarlo con node (scripts/probar-precios.mjs).
//
// La regla de fondo: nunca se pisa un valor escrito. Las celdas vacías se
// llenan; si la fila ya tiene otro precio, se muestra la sugerencia y el
// docente decide con «Usar». Nada se guarda hasta que pulsa Guardar.

const valido = (x) => typeof x === "number" && Number.isFinite(x) && x >= 0 && x < 10000;

/** Si dos precios están a más de 10 veces uno del otro (o uno es cero y el otro no). */
export function muyDistinto(a, b) {
  if (a === b) return false;
  const [menor, mayor] = [Math.min(a, b), Math.max(a, b)];
  return menor <= 0 || mayor / menor > 10;
}

/** Por qué conviene mirar una sugerencia antes de usarla, o null. `guardado` es [entrada, salida] de PRECIOS_API. */
export function motivoRevisar(sugerido, guardado) {
  if (sugerido.entrada > sugerido.salida) return "La entrada sale más cara que la salida: revísalo.";
  if (Array.isArray(guardado) && guardado.length === 2
    && (muyDistinto(Number(guardado[0]), sugerido.entrada) || muyDistinto(Number(guardado[1]), sugerido.salida))) {
    return "Es más de 10 veces distinto de lo guardado: revísalo.";
  }
  return null;
}

/**
 * Qué hacer con una fila. `escrito` es lo que tienen sus celdas ({ entrada,
 * salida }, "" si vacía), `guardado` lo de PRECIOS_API y `sugerido` lo que
 * trajo el sitio (o null). Devuelve { accion, entrada, salida, revisar }:
 *   "llenar"     se escriben las celdas vacías (entrada y salida, como texto)
 *   "igual"      ya tiene ese precio
 *   "distinta"   tiene otro: se muestra la sugerencia con «Usar»
 *   "ambiguo"    la fuente lo trae a varios precios (`duda` es su aviso): queda como está
 *   "sin-dato"   la fuente no trae el modelo: la fila queda como está
 */
export function decidirFila(escrito, guardado, sugerido, duda = null) {
  if (!sugerido || !valido(sugerido.entrada) || !valido(sugerido.salida)) return { accion: duda ? "ambiguo" : "sin-dato" };
  const revisar = motivoRevisar(sugerido, guardado);
  const celdas = [[escrito.entrada, sugerido.entrada], [escrito.salida, sugerido.salida]];
  if (celdas.some(([v, s]) => v !== "" && Number(v) !== s)) return { accion: "distinta", revisar };
  if (celdas.every(([v]) => v !== "")) return { accion: "igual", revisar };
  const [entrada, salida] = celdas.map(([v, s]) => (v === "" ? comoCelda(s) : v));
  return { accion: "llenar", entrada, salida, revisar };
}

/** Un precio como se escribe en la celda, sin el ruido de coma flotante (0.18000000000000002 -> "0.18"). */
export const comoCelda = (x) => String(Number(x.toPrecision(12)));

/** "0.75 / 4.5": los dos precios, como se escriben en las celdas. */
export const textoPrecio = (s) => `${s.entrada} / ${s.salida}`;

/** De dónde salió un precio: "OpenAI", y el nombre con que se encontró si no era el pedido. */
export function textoOrigen(s) {
  return s.como ? `${s.proveedor}, como ${s.como}` : s.proveedor;
}

/** "02-11-2026" a partir del ISO que guarda el Worker. */
export function fechaConsulta(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("es-CL", { day: "2-digit", month: "2-digit", year: "numeric" });
}

/** Una línea con lo que pasó: "Se llenaron 5 modelos; 1 tiene otro precio (pulsa «Usar» si corresponde); 1 sin dato en la fuente." */
export function resumenDecisiones(decisiones) {
  const n = (a) => decisiones.filter((d) => d.accion === a).length;
  const partes = [];
  if (n("llenar")) partes.push(n("llenar") === 1 ? "Se llenó 1 modelo" : `Se llenaron ${n("llenar")} modelos`);
  if (n("igual")) partes.push(`${n("igual")} ya ${n("igual") === 1 ? "tenía" : "tenían"} ese precio`);
  if (n("distinta")) {
    partes.push(`${n("distinta")} ${n("distinta") === 1 ? "tiene" : "tienen"} otro precio (pulsa «Usar» si corresponde)`);
  }
  if (n("ambiguo")) partes.push(`${n("ambiguo")} con varios precios en la fuente`);
  if (n("sin-dato")) partes.push(`${n("sin-dato")} sin dato en la fuente`);
  const revisar = decisiones.filter((d) => d.revisar && d.accion !== "sin-dato").length;
  if (revisar) partes.push(`${revisar} para revisar`);
  if (!partes.length) return "";
  const texto = partes.join("; ");
  return `${texto[0].toUpperCase()}${texto.slice(1)}.`;
}

/** El nombre de modelo que acepta el sitio: el mismo NOMBRE_MODELO de src/precios.ts. */
export const NOMBRE_MODELO = /^(?=.{2,60}$)(?!.*\.\.)[A-Za-z0-9._:-]+(?:\/[A-Za-z0-9._:-]+){0,2}$/;

/** Solo enlaces https: lo que viene de la fuente no puede ser un javascript:. */
export const enlaceSeguro = (x) => (typeof x === "string" && /^https:\/\//.test(x) ? x : null);
