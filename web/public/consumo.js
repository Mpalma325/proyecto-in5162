// Lo que se gasta en la API. Cada trabajo que llama al modelo deja al terminar
// una línea por modelo en su salida (modulos/ia/cliente.py):
//
//   Consumo de API (gpt-5.4-mini): 3 llamadas, 7512 tokens de entrada, 1830 de salida.
//
// Acá se leen esas líneas y se multiplican por los precios que se cargan en
// Configuración › Parámetros (US$ por millón de tokens, [entrada, salida]).
// Sin precio para un modelo, se muestran los tokens y se avisa.

const LINEA = /^Consumo de API \(([^)]+)\): (\d+) llamadas?, (\d+) tokens de entrada, (\d+) de salida/;

/** Las líneas de consumo de un texto (la salida de un trabajo): [{ modelo, llamadas, entrada, salida }]. */
export function leerConsumo(texto) {
  return String(texto || "").split("\n").map((l) => l.trim().match(LINEA)).filter(Boolean)
    .map((m) => ({ modelo: m[1], llamadas: Number(m[2]), entrada: Number(m[3]), salida: Number(m[4]) }));
}

/** Los precios guardados, { modelo: [entrada, salida] }, a partir de PRECIOS_API. */
export function leerPrecios(texto) {
  try {
    const o = JSON.parse(texto || "{}");
    return o && typeof o === "object" && !Array.isArray(o) ? o : {};
  } catch {
    return {};
  }
}

/**
 * La suma de varios consumos: { llamadas, entrada, salida, usd, sinPrecio }.
 * `usd` cuenta solo los modelos con precio; `sinPrecio` dice cuáles faltan.
 */
export function sumarConsumo(consumos, precios) {
  const total = { llamadas: 0, entrada: 0, salida: 0, usd: 0, sinPrecio: [] };
  for (const c of consumos) {
    total.llamadas += c.llamadas;
    total.entrada += c.entrada;
    total.salida += c.salida;
    const p = precios[c.modelo];
    if (Array.isArray(p) && p.length === 2) total.usd += (c.entrada * p[0] + c.salida * p[1]) / 1e6;
    else if (!total.sinPrecio.includes(c.modelo)) total.sinPrecio.push(c.modelo);
  }
  return total;
}

/** "US$ 0,42", con más decimales mientras más chico: los centavos de un trabajo no se pierden. */
export function formatoUsd(n) {
  const decimales = n === 0 ? 2 : n < 0.01 ? 4 : n < 1 ? 3 : 2;
  return `US$ ${n.toLocaleString("es-CL", { minimumFractionDigits: decimales, maximumFractionDigits: decimales })}`;
}

const miles = (n) => n.toLocaleString("es-CL");

/** Una línea para mostrar: "US$ 0,0042 · 3 llamadas · 9.342 tokens", o los tokens si falta el precio. */
export function textoConsumo(total) {
  const tokens = `${miles(total.llamadas)} ${total.llamadas === 1 ? "llamada" : "llamadas"} · `
    + `${miles(total.entrada + total.salida)} tokens`;
  if (!total.llamadas) return "";
  return total.sinPrecio.length && !total.usd ? `${tokens} (sin precio para ${total.sinPrecio.join(", ")})`
    : `${formatoUsd(total.usd)} · ${tokens}${total.sinPrecio.length ? ` (sin precio para ${total.sinPrecio.join(", ")})` : ""}`;
}
