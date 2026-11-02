// Las cuentas de "Probar criterio", sin pantalla: cuánto costaría una prueba,
// en qué semanas se usó cada versión del prompt y el resumen de una
// comparación. La vista está en probar.js; esto se prueba sin navegador
// (web/scripts/probar-criterio.mjs).

import { sumarConsumo } from "./consumo.js";

// Tokens por carácter de un prompt en español: alcanza para estimar cuánto
// cambia el costo cuando el candidato es más largo o más corto que el vigente.
const CARACTERES_POR_TOKEN = 4;

/**
 * Lo que costó en promedio corregir una respuesta, a partir de los trabajos
 * reales de evaluación y de prueba de criterio que ya corrieron:
 * { entrada, salida, modelo, llamadas } por llamada, o null si no hay datos.
 * `consumos` es lo de /api/consumo (del más nuevo al más viejo), con las
 * líneas ya leídas: [{ flujo, prueba, usos: [{ modelo, llamadas, entrada, salida }] }].
 */
export function consumoPorRespuesta(consumos) {
  const usos = consumos.filter((c) => !c.prueba && (c.flujo === "tests.evaluar" || c.flujo === "tests.experimento"))
    .flatMap((c) => c.usos);
  const llamadas = usos.reduce((a, u) => a + u.llamadas, 0);
  if (!llamadas) return null;
  return {
    entrada: usos.reduce((a, u) => a + u.entrada, 0) / llamadas,
    salida: usos.reduce((a, u) => a + u.salida, 0) / llamadas,
    // El modelo de la corrida más reciente: es el que se va a usar.
    modelo: usos[0].modelo,
    llamadas,
  };
}

/**
 * Cuánto costaría reevaluar `n` respuestas con un prompt de `largoCandidato`
 * caracteres, si el vigente tiene `largoVigente`: lo mismo que suma la página
 * para un trabajo terminado ({ llamadas, entrada, salida, usd, sinPrecio }).
 */
export function estimarCosto({ n, porRespuesta, largoCandidato, largoVigente, precios }) {
  if (!porRespuesta || !(n > 0)) return null;
  const extra = (largoCandidato - largoVigente) / CARACTERES_POR_TOKEN;
  const entrada = Math.max(0, Math.round(n * (porRespuesta.entrada + extra)));
  return sumarConsumo([{ modelo: porRespuesta.modelo, llamadas: n, entrada,
    salida: Math.round(n * porRespuesta.salida) }], precios);
}

/** La huella de un texto, igual que modulos/ia/versiones.py: sha256 del texto sin \r ni bordes, 8 caracteres. */
export async function huella(texto) {
  const normal = String(texto).replace(/\r\n/g, "\n").trim();
  const bytes = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(normal)));
  return [...bytes.slice(0, 4)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** "evaluar_respuesta.md@1a2b3c4d; pauta.md@…" -> "1a2b3c4d" (la versión del prompt de corrección). */
export function huellaDelPrompt(versiones) {
  const m = String(versiones || "").match(/(?:^|;\s*)evaluar_respuesta\.md@([0-9a-f]{8})/);
  return m ? m[1] : null;
}

/** En qué semanas se corrigió con cada versión, según la columna Versiones del log: { huella: [semanas] }. */
export function semanasPorVersion(filasLog) {
  const por = {};
  for (const f of filasLog) {
    if (f.Flujo !== "test" || f.Evento !== "evaluacion") continue;
    const h = huellaDelPrompt(f.Versiones);
    if (!h) continue;
    (por[h] ??= new Set()).add(Number(f.Item));
  }
  return Object.fromEntries(Object.entries(por).map(([h, s]) => [h, [...s].filter((x) => x >= 0).sort((a, b) => a - b)]));
}

/** [1,2,3,5,7,8] -> "1 a 3, 5, 7 y 8". */
export function rangos(semanas) {
  const tramos = [];
  for (const s of semanas) {
    const ultimo = tramos.at(-1);
    if (ultimo && s === ultimo[1] + 1) ultimo[1] = s;
    else tramos.push([s, s]);
  }
  const textos = tramos.map(([a, b]) => (a === b ? String(a) : b === a + 1 ? `${a}, ${b}` : `${a} a ${b}`));
  return textos.length > 1 ? `${textos.slice(0, -1).join(", ")} y ${textos.at(-1)}` : textos[0] || "";
}

const numero = (v) => {
  const x = Number(String(v ?? "").replace(",", "."));
  return String(v ?? "").trim() === "" || Number.isNaN(x) ? null : x;
};

// Las categorías de originalidad, de menos a más (modulos/datos/agregaciones.py).
export const NIVELES = ["Muy Baja", "Baja", "Media", "Alta", "Muy Alta"];

/**
 * El resumen de una prueba de criterio, desde las filas del CSV que deja
 * experimento.py: notas medias, cuántas subieron o bajaron, y la
 * originalidad antes y después por categoría.
 */
export function resumirComparacion(filas) {
  const pares = filas.map((f) => [numero(f.NotaAntes), numero(f.NotaDespues)]).filter(([a, d]) => a !== null && d !== null);
  const media = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
  const deltas = filas.map((f) => numero(f.DeltaNota)).filter((d) => d !== null);
  const niveles = filas.map((f) => numero(f.DeltaNivel)).filter((d) => d !== null);
  const contar = (columna) => Object.fromEntries(NIVELES.map((n) => [n, filas.filter((f) => f[columna] === n).length]));
  return {
    total: filas.length,
    sinFormato: filas.filter((f) => f.FormatoOK === "NO").length,
    mediaAntes: media(pares.map(([a]) => a)),
    mediaDespues: media(pares.map(([, d]) => d)),
    notas: { suben: deltas.filter((d) => d > 0).length, bajan: deltas.filter((d) => d < 0).length,
      iguales: deltas.filter((d) => d === 0).length },
    originalidad: { suben: niveles.filter((d) => d > 0).length, bajan: niveles.filter((d) => d < 0).length,
      iguales: niveles.filter((d) => d === 0).length },
    antes: contar("OriginalidadAntes"),
    despues: contar("OriginalidadDespues"),
  };
}

/** Las filas que más cambiaron primero; las que no se pudieron leer, al final. */
export function ordenarPorCambio(filas) {
  const peso = (f) => {
    const d = numero(f.DeltaNota);
    return d === null ? -1 : Math.abs(d) + Math.abs(numero(f.DeltaNivel) || 0) / 10;
  };
  return [...filas].sort((a, b) => peso(b) - peso(a));
}

/** Una nota como la ve el alumno: 6.5 -> "6,5", 5 -> "5,0"; vacía -> "—". */
export function textoNota(v) {
  const x = numero(v);
  return x === null ? "—" : x.toLocaleString("es-CL", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
}
