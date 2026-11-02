// Lo que se gasta en la API. Cada trabajo que llama al modelo deja al terminar
// una línea por modelo en su salida (modulos/ia/cliente.py):
//
//   Consumo de API (gpt-5.4-mini): 3 llamadas, 7512 tokens de entrada (6144 en caché), 1830 de salida, US$ 0,009722.
//
// "(N en caché)" va solo si el proveedor sacó parte de la entrada de su caché,
// y el US$ solo si el motor tenía precio para el modelo. Ese US$ es lo que
// costó con los precios de ese momento, y es el que vale: cambiar un precio en
// Configuración › Parámetros no cambia lo que costó un trabajo viejo. Las
// líneas sin US$ (las de antes, o sin precio en su momento) se calculan con
// los precios de hoy. Sin precio para un modelo, se muestran los tokens y se avisa.

const LINEA = /^Consumo de API \(([^)]+)\): (\d+) llamadas?, (\d+) tokens de entrada(?: \((\d+) en caché\))?, (\d+) de salida(?:, US\$ (\d+(?:,\d+)?))?/;

/**
 * Las líneas de consumo de un texto (la salida de un trabajo):
 * [{ modelo, llamadas, entrada, cache, salida, usd }]. `usd` es el costo del
 * momento, o null si la línea no lo trae.
 */
export function leerConsumo(texto) {
  return String(texto || "").split("\n").map((l) => l.trim().match(LINEA)).filter(Boolean)
    .map((m) => ({ modelo: m[1], llamadas: Number(m[2]), entrada: Number(m[3]), cache: Number(m[4] || 0),
      salida: Number(m[5]), usd: m[6] === undefined ? null : Number(m[6].replace(",", ".")) }));
}

/** Los precios guardados, { modelo: [entrada, salida] o [entrada, salida, caché] }, a partir de PRECIOS_API. */
export function leerPrecios(texto) {
  try {
    const o = JSON.parse(texto || "{}");
    return o && typeof o === "object" && !Array.isArray(o) ? o : {};
  } catch {
    return {};
  }
}

const valido = (x) => typeof x === "number" && Number.isFinite(x) && x >= 0;

/** El precio de un modelo como { entrada, salida, cache }, o null. Sin el tercero, la caché se cobra como entrada. */
export function tarifa(p) {
  if (!Array.isArray(p) || (p.length !== 2 && p.length !== 3) || !p.every(valido)) return null;
  return { entrada: p[0], salida: p[1], cache: p.length === 3 ? p[2] : p[0] };
}

/** US$ de un consumo con una tarifa: la entrada en caché va a su precio, el resto de la entrada al suyo. */
export function costo(c, t) {
  const cache = Math.min(c.cache || 0, c.entrada);
  return ((c.entrada - cache) * t.entrada + cache * t.cache + c.salida * t.salida) / 1e6;
}

/**
 * La suma de varios consumos: { llamadas, entrada, cache, salida, usd, sinPrecio, delMomento, deHoy }.
 * Cada línea suma su US$ si lo trae; si no, se calcula con los precios de hoy.
 * `sinPrecio` dice qué modelos quedaron sin costo; `delMomento` y `deHoy`
 * cuentan las líneas de cada origen, para avisar cuando se mezclan.
 */
export function sumarConsumo(consumos, precios) {
  const total = { llamadas: 0, entrada: 0, cache: 0, salida: 0, usd: 0, sinPrecio: [], delMomento: 0, deHoy: 0 };
  for (const c of consumos) {
    total.llamadas += c.llamadas;
    total.entrada += c.entrada;
    total.cache += c.cache || 0;
    total.salida += c.salida;
    const t = tarifa(precios[c.modelo]);
    if (valido(c.usd)) {
      total.usd += c.usd;
      total.delMomento++;
    } else if (t) {
      total.usd += costo(c, t);
      total.deHoy++;
    } else if (!total.sinPrecio.includes(c.modelo)) total.sinPrecio.push(c.modelo);
  }
  return total;
}

/** "US$ 0,42", con más decimales mientras más chico: los centavos de un trabajo no se pierden. */
export function formatoUsd(n) {
  const decimales = n === 0 ? 2 : n < 0.01 ? 4 : n < 1 ? 3 : 2;
  return `US$ ${n.toLocaleString("es-CL", { minimumFractionDigits: decimales, maximumFractionDigits: decimales })}`;
}

const miles = (n) => n.toLocaleString("es-CL");

/** Cuando una suma junta costos del momento con otros calculados con los precios de hoy, una nota corta; si no, "". */
export function notaMezcla(total) {
  return total.delMomento && total.deHoy ? "parte calculada con los precios de hoy" : "";
}

/** Una línea para mostrar: "US$ 0,0042 · 3 llamadas · 9.342 tokens (6.144 en caché)", o los tokens si falta el precio. */
export function textoConsumo(total) {
  if (!total.llamadas) return "";
  const tokens = `${miles(total.llamadas)} ${total.llamadas === 1 ? "llamada" : "llamadas"} · `
    + `${miles(total.entrada + total.salida)} tokens`;
  // La caché y los avisos en un solo paréntesis: "(6.144 en caché; parte calculada…)".
  const partes = [total.cache ? `${miles(total.cache)} en caché` : "",
    total.sinPrecio.length ? `sin precio para ${total.sinPrecio.join(", ")}` : "", notaMezcla(total)]
    .filter(Boolean);
  const notas = partes.length ? ` (${partes.join("; ")})` : "";
  return total.sinPrecio.length && !total.usd ? `${tokens}${notas}` : `${formatoUsd(total.usd)} · ${tokens}${notas}`;
}
