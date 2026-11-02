// Las versiones de un prompt que se usaron de verdad para corregir, sin
// pantalla: cuáles hay, en qué semanas o tareas se usó cada una y qué cambia
// entre dos textos. La vista está en datos.js (Configuración › La IA ›
// Prompts); esto se prueba sin navegador (web/scripts/probar-historial.mjs).
//
// El motor guarda cada versión la primera vez que corrige con ella, en
// <flujo>/prompts_usados/<nombre>@<huella>.<ext> (modulos/ia/versiones.py), y
// anota la huella en la columna Versiones del log.

import { huella } from "./criterio.js";
import { leerCsv } from "./csv.js";

export { huella };

// La carpeta de cada flujo y cómo lo nombra la columna Flujo del log (modulos/datos/esquema.py).
const FLUJO_DEL_LOG = { tests_semanales: "test", tareas: "tarea" };

// Celdas de la tabla del diff (líneas de un texto × líneas del otro). Un prompt
// de 30 mil caracteres tiene unas 600 líneas: 360 mil celdas. Más que esto ya
// no es un prompt y la tabla trabaría la página.
const TOPE_DIFF = 2_000_000;

const escapar = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** "tests_semanales/prompts/evaluar_respuesta.md" -> { flujo, nombre, base, ext }. */
function partes(ruta) {
  const [flujo, , nombre = ""] = String(ruta).split("/");
  const punto = nombre.lastIndexOf(".");
  return punto > 0
    ? { flujo, nombre, base: nombre.slice(0, punto), ext: nombre.slice(punto + 1) }
    : { flujo, nombre, base: nombre, ext: "" };
}

/**
 * Las versiones guardadas del prompt de `ruta`, desde la lista de archivos del
 * semestre (rutas sueltas o los { ruta, subido, … } de /api/archivos):
 * [{ ruta, huella, subido }]. Las pautas y los candidatos de Probar criterio
 * no tienen archivo de prompt y no aparecen.
 */
export function versionesDe(ruta, archivos) {
  const { flujo, base, ext } = partes(ruta);
  if (!flujo || !base) return [];
  const patron = new RegExp(`^${escapar(flujo)}/prompts_usados/${escapar(base)}@([0-9a-f]{8})${ext ? `\\.${escapar(ext)}` : ""}$`);
  return archivos.map((a) => (typeof a === "string" ? { ruta: a } : a))
    .map((a) => [a, String(a.ruta).match(patron)]).filter(([, m]) => m)
    .map(([a, m]) => ({ ruta: m[0], huella: m[1], subido: a.subido || null }));
}

/** Las filas de log_envios.csv como objetos {columna: valor}. */
export function filasDelLog(texto) {
  const { columnas, filas } = leerCsv(texto);
  return filas.map((f) => Object.fromEntries(columnas.map((c, i) => [c, f[i] ?? ""])));
}

const momento = (t) => {
  const x = Date.parse(t);
  return Number.isNaN(x) ? null : x;
};

/**
 * En qué semanas o tareas se usó cada huella del prompt de `ruta`, según la
 * columna Versiones del log: { huella: { items, eventos, primero, ultimo } }.
 * Cuenta cualquier evento que la traiga (corrección, tutoría, correo), pero
 * solo del flujo del prompt: tests y tareas tienen prompts con el mismo nombre.
 * `items` son las semanas (números) o las tareas ("T1"), ordenadas; `primero` y
 * `ultimo` son el Timestamp del log, o null si ninguno se pudo leer.
 */
export function usosPorHuella(ruta, filasLog) {
  const { flujo, nombre } = partes(ruta);
  const delLog = FLUJO_DEL_LOG[flujo];
  // "candidato@…" y "@sin-registro" no calzan: no son versiones con archivo.
  const patron = new RegExp(`^${escapar(nombre)}@([0-9a-f]{8})$`);
  const por = {};
  for (const f of filasLog) {
    if (delLog && f.Flujo !== delLog) continue;
    for (const parte of String(f.Versiones || "").split(";")) {
      const m = parte.trim().match(patron);
      if (!m) continue;
      const u = (por[m[1]] ??= { items: new Set(), eventos: 0, primero: null, ultimo: null });
      u.eventos++;
      const item = String(f.Item ?? "").trim();
      if (item) u.items.add(item);
      const t = momento(f.Timestamp);
      if (t !== null) {
        if (u.primero === null || t < momento(u.primero)) u.primero = f.Timestamp;
        if (u.ultimo === null || t > momento(u.ultimo)) u.ultimo = f.Timestamp;
      }
    }
  }
  return Object.fromEntries(Object.entries(por).map(([h, u]) => [h, { ...u, items: ordenarItems([...u.items]) }]));
}

/** Semanas como números de menor a mayor; las tareas, T2 antes que T10. */
function ordenarItems(items) {
  if (items.every((x) => /^\d+$/.test(x))) return items.map(Number).sort((a, b) => a - b);
  return items.sort((a, b) => a.localeCompare(b, "es", { numeric: true }));
}

// Como rangos() de criterio.js, pero dos seguidas son dos elementos de la
// enumeración: "1, 2, 4 y 5" (rangos() da "1, 2 y 4, 5").
const tramos = (numeros) => {
  const grupos = [];
  for (const x of numeros) {
    const ultimo = grupos.at(-1);
    if (ultimo && x === ultimo[1] + 1) ultimo[1] = x;
    else grupos.push([x, x]);
  }
  return enumerar(grupos.flatMap(([a, b]) => (a === b ? [String(a)] : b === a + 1 ? [String(a), String(b)] : [`${a} a ${b}`])));
};
const enumerar = (xs) => (xs.length > 1 ? `${xs.slice(0, -1).join(", ")} y ${xs.at(-1)}` : xs[0] || "");

/**
 * Los usos para mostrar: "semanas 1 a 3 y 5", "semana 4", "T1 y T2", o "sin
 * usos registrados en el log" si `uso` no existe o no tiene semanas ni tareas.
 */
export function textoUsos(uso) {
  const items = uso?.items || [];
  if (!items.length) return "sin usos registrados en el log";
  if (items.every((x) => typeof x === "number")) {
    return `${items.length === 1 ? "semana" : "semanas"} ${tramos(items)}`;
  }
  if (items.every((x) => /^T\d+$/.test(x))) {
    return tramos(items.map((x) => Number(x.slice(1))).sort((a, b) => a - b)).replace(/\d+/g, "T$&");
  }
  return enumerar(items);
}

/**
 * De la última usada a la más vieja; las que el log no registra, al final
 * (entre ellas, la subida más nueva primero). No cambia `versiones`.
 */
export function ordenarVersiones(versiones, usos = {}) {
  const ultimo = (v) => momento(usos[v.huella]?.ultimo) ?? -Infinity;
  const usada = (v) => (usos[v.huella]?.eventos ? 1 : 0);
  const subido = (v) => momento(v.subido) ?? -Infinity;
  return [...versiones].sort((a, b) => usada(b) - usada(a) || ultimo(b) - ultimo(a)
    || subido(b) - subido(a) || a.huella.localeCompare(b.huella));
}

/** Las líneas de un texto, sin \r y sin el salto final (que no se ve como cambio). */
function lineas(texto) {
  const normal = String(texto ?? "").replace(/\r\n?/g, "\n").replace(/\n$/, "");
  return normal === "" ? [] : normal.split("\n");
}

/** Junta en bloques las líneas seguidas del mismo tipo. */
function agrupar(marcas) {
  const bloques = [];
  for (const [tipo, linea] of marcas) {
    const ultimo = bloques.at(-1);
    if (ultimo && ultimo.tipo === tipo) ultimo.lineas.push(linea);
    else bloques.push({ tipo, lineas: [linea] });
  }
  return bloques;
}

/**
 * Qué líneas cambian de `antes` a `despues`, por la subsecuencia común más
 * larga: { bloques: [{ tipo: "igual" | "agrega" | "quita", lineas }], aviso }.
 * En un cambio, lo que se quita va antes que lo que se agrega. Si el tramo
 * distinto pasa de `tope` celdas, no se compara línea a línea: se da todo lo
 * de antes como quitado y todo lo de después como agregado, con un `aviso`
 * (null cuando la comparación es completa).
 */
export function diffLineas(antes, despues, { tope = TOPE_DIFF } = {}) {
  const a = lineas(antes);
  const b = lineas(despues);
  // Lo igual al principio y al final no entra en la tabla: casi siempre es casi todo.
  let ini = 0;
  while (ini < a.length && ini < b.length && a[ini] === b[ini]) ini++;
  let fin = 0;
  while (fin < a.length - ini && fin < b.length - ini && a[a.length - 1 - fin] === b[b.length - 1 - fin]) fin++;
  const medioA = a.slice(ini, a.length - fin);
  const medioB = b.slice(ini, b.length - fin);
  const marcas = a.slice(0, ini).map((l) => ["igual", l]);
  let aviso = null;

  const n = medioA.length;
  const m = medioB.length;
  if ((n + 1) * (m + 1) > tope) {
    aviso = `Los textos son demasiado largos para compararlos línea a línea (${n} y ${m} líneas distintas): `
      + "se muestra todo lo distinto como quitado y agregado.";
    // Con bucles: push(...lista) pasa cada línea como argumento y con cientos de
    // miles revienta la pila, justo en el camino que debía degradar.
    for (const l of medioA) marcas.push(["quita", l]);
    for (const l of medioB) marcas.push(["agrega", l]);
  } else {
    // largo[i][j]: la subsecuencia común más larga entre medioA[i:] y medioB[j:].
    const ancho = m + 1;
    const largo = new Uint32Array((n + 1) * ancho);
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m - 1; j >= 0; j--) {
        largo[i * ancho + j] = medioA[i] === medioB[j]
          ? largo[(i + 1) * ancho + j + 1] + 1
          : Math.max(largo[(i + 1) * ancho + j], largo[i * ancho + j + 1]);
      }
    }
    let i = 0;
    let j = 0;
    while (i < n || j < m) {
      if (i < n && j < m && medioA[i] === medioB[j]) { marcas.push(["igual", medioA[i]]); i++; j++; }
      else if (j >= m || (i < n && largo[(i + 1) * ancho + j] >= largo[i * ancho + j + 1])) { marcas.push(["quita", medioA[i]]); i++; }
      else { marcas.push(["agrega", medioB[j]]); j++; }
    }
  }
  for (const l of a.slice(a.length - fin)) marcas.push(["igual", l]);
  return { bloques: agrupar(marcas), aviso };
}

/** Cuántas líneas agrega y quita un diff: { agregadas, quitadas }. */
export function contarCambios(bloques) {
  const contar = (tipo) => bloques.filter((x) => x.tipo === tipo).reduce((s, x) => s + x.lineas.length, 0);
  return { agregadas: contar("agrega"), quitadas: contar("quita") };
}
