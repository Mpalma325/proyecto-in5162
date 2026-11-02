/**
 * Precios sugeridos de la API, para no cargar a mano el de cada modelo en
 * Configuración › Parámetros.
 *
 * Se leen de listas públicas con muchos proveedores (OpenAI, Anthropic, Google,
 * Mistral, DeepSeek...). Cada fuente es una entrada de FUENTES: su lector la
 * convierte a una tabla común y la búsqueda no sabe de dónde vino. Cambiar de
 * fuente, o agregar otra, es agregar una entrada.
 *
 * Nada de esto guarda: el sitio sugiere, el docente revisa y pulsa Guardar.
 * Todo menos traerFuente() es puro, para probarlo sin red
 * (scripts/probar-precios.mjs).
 */

/**
 * Un nombre de modelo, solo o con su proveedor adelante ("openai/gpt-5.4-mini",
 * como lo escriben los intermediarios tipo OpenRouter). Lo usan MODELO,
 * PRECIOS_API y /api/precios-sugeridos.
 */
export const NOMBRE_MODELO = /^(?=.{2,60}$)(?!.*\.\.)[A-Za-z0-9._:-]+(?:\/[A-Za-z0-9._:-]+){0,2}$/;

/** El rango que acepta PRECIOS_API, en US$ por millón de tokens. */
export const precioValido = (x: unknown): x is number =>
  typeof x === "number" && Number.isFinite(x) && x >= 0 && x < 10000;

/**
 * PRECIOS_API: {"modelo": [entrada, salida]}, o [entrada, salida, caché] si el
 * proveedor cobra aparte la entrada en caché. Los escribe quien administra el
 * curso; el sitio solo multiplica. Una tabla guardada con dos valores sigue valiendo.
 */
export function preciosValidos(v: string): boolean {
  if (v.length > 4000) return false;
  try {
    const o = JSON.parse(v);
    return esObjeto(o) && Object.entries(o).every(([m, p]) =>
      NOMBRE_MODELO.test(m) && Array.isArray(p) && (p.length === 2 || p.length === 3) && p.every(precioValido));
  } catch {
    return false;
  }
}

/** Lo que cobra un proveedor por un modelo, en US$ por millón de tokens. */
export interface Oferta {
  entrada: number;
  salida: number;
  /** La entrada en caché, si la fuente la trae. */
  cache: number | null;
  /** Como lo nombra la fuente ("openai", "azure"): con esto se compara un prefijo. */
  proveedor: string;
  /** Para mostrar ("OpenAI"). */
  nombreProveedor: string;
  /** Según la fuente, este proveedor es quien hace el modelo y no un revendedor. */
  fabricante: boolean;
  /** Su página de precios, si la fuente la trae. */
  enlace: string | null;
}

/** Nombre del modelo -> quienes lo cobran. Un modelo puede estar con varios nombres (sus alias). */
export type Tabla = Map<string, Oferta[]>;

export interface Fuente {
  nombre: string;
  url: string;
  /** Dónde puede ver la fuente el docente. */
  enlace: string;
  /** Convierte lo que baja de `url` a la tabla común. `hoy` es "AAAA-MM-DD". */
  leer: (datos: unknown, hoy: string) => Tabla;
}

/** 0.18000000000000002 -> 0.18: el ruido de coma flotante de alguna fuente no llega a la celda. */
const limpio = (x: unknown): unknown => (typeof x === "number" ? Number(x.toPrecision(12)) : x);

function agregar(tabla: Tabla, nombre: string, oferta: Oferta): void {
  // La caché es opcional: si la fuente no la trae o la trae rara, queda sin ella y el resto vale igual.
  const cache = limpio(oferta.cache);
  oferta = { ...oferta, entrada: limpio(oferta.entrada) as number, salida: limpio(oferta.salida) as number,
    cache: precioValido(cache) ? cache : null };
  const lista = tabla.get(nombre);
  if (lista) lista.push(oferta); else tabla.set(nombre, [oferta]);
}

const enlaceSeguro = (x: unknown): string | null =>
  typeof x === "string" && /^https:\/\/[^\s"<>]{1,300}$/.test(x) ? x : null;

// ---------------------------------------------------------------- genai-prices

type Objeto = Record<string, unknown>;
const esObjeto = (x: unknown): x is Objeto => Boolean(x) && typeof x === "object" && !Array.isArray(x);

/**
 * Si una regla de genai-prices acepta el nombre (equals, starts_with,
 * contains, regex, or, and). No se usa para encontrar modelos, que sería
 * demasiado laxo: solo para saber si el id de un modelo es un nombre real y
 * qué proveedor hace los modelos que se llaman así (su model_match).
 */
export function coincide(regla: unknown, nombre: string): boolean {
  if (!esObjeto(regla)) return false;
  if (Array.isArray(regla.or)) return regla.or.some((r) => coincide(r, nombre));
  if (Array.isArray(regla.and)) return regla.and.length > 0 && regla.and.every((r) => coincide(r, nombre));
  if (typeof regla.equals === "string") return nombre === regla.equals;
  if (typeof regla.starts_with === "string") return nombre.startsWith(regla.starts_with);
  if (typeof regla.ends_with === "string") return nombre.endsWith(regla.ends_with);
  if (typeof regla.contains === "string") return nombre.includes(regla.contains);
  if (typeof regla.regex === "string") {
    try { return new RegExp(regla.regex).test(nombre); } catch { return false; }
  }
  return false;
}

/** Los nombres exactos de una regla: sus equals, también dentro de un or. */
function nombresExactos(regla: unknown): string[] {
  if (!esObjeto(regla)) return [];
  if (typeof regla.equals === "string") return [regla.equals];
  return Array.isArray(regla.or) ? regla.or.flatMap(nombresExactos) : [];
}

/** Un precio es un número o { base, tiers } por tramos de largo: vale la base, hasta el primer tramo. */
const base = (x: unknown): unknown => (esObjeto(x) && "base" in x ? x.base : x);

/**
 * Los precios vigentes hoy. Algunos modelos traen una lista de precios con
 * fecha de inicio (constraint.start_date): vale el último que ya empezó. Si
 * dependen de otra cosa, como la hora del día, no hay un precio único y no se
 * sugiere ninguno.
 */
export function preciosDeHoy(precios: unknown, hoy: string): Objeto | null {
  if (!Array.isArray(precios)) return esObjeto(precios) ? precios : null;
  let elegido: unknown = null;
  let desde = "";
  for (const p of precios) {
    if (!esObjeto(p)) continue;
    const c = esObjeto(p.constraint) ? p.constraint : {};
    if (Object.keys(c).some((k) => k !== "start_date")) return null;
    const inicio = typeof c.start_date === "string" ? c.start_date : "";
    if (inicio <= hoy && inicio >= desde) {
      elegido = p.prices;
      desde = inicio;
    }
  }
  return esObjeto(elegido) ? elegido : null;
}

/**
 * genai-prices (Pydantic): una lista de proveedores, cada uno con sus modelos.
 * Un modelo se encuentra por su id (si su propia regla lo acepta) o por uno de
 * sus alias exactos. Quién fabrica qué lo dice el model_match del proveedor:
 * el de OpenAI acepta "gpt-...", el de Anthropic "claude...". Azure, Bedrock
 * u OpenRouter no tienen, porque revenden modelos ajenos.
 */
export function leerGenaiPrices(datos: unknown, hoy: string): Tabla {
  if (!Array.isArray(datos)) throw new Error("no trae la lista de proveedores");
  const tabla: Tabla = new Map();
  for (const p of datos) {
    if (!esObjeto(p) || typeof p.id !== "string" || !Array.isArray(p.models)) continue;
    const nombreProveedor = typeof p.name === "string" ? p.name : p.id;
    const enlace = Array.isArray(p.pricing_urls) ? enlaceSeguro(p.pricing_urls[0]) : null;
    for (const m of p.models) {
      if (!esObjeto(m) || typeof m.id !== "string") continue;
      const precios = preciosDeHoy(m.prices, hoy);
      if (!precios) continue;
      const nombres = new Set(nombresExactos(m.match));
      if (coincide(m.match, m.id)) nombres.add(m.id);
      for (const n of nombres) {
        agregar(tabla, n, {
          entrada: base(precios.input_mtok) as number, salida: base(precios.output_mtok) as number,
          cache: base(precios.cache_read_mtok) as number | null, proveedor: p.id, nombreProveedor, fabricante: coincide(p.model_match, n), enlace,
        });
      }
    }
  }
  return tabla;
}

// ---------------------------------------------------------------- llm-prices

/**
 * llm-prices.com (Simon Willison): una lista plana de modelos agrupada por
 * quien los hace (vendor), sin revendedores ni páginas de precios.
 */
export function leerLlmPrices(datos: unknown): Tabla {
  const lista = esObjeto(datos) ? datos.prices : null;
  if (!Array.isArray(lista)) throw new Error("no trae la lista de precios");
  const tabla: Tabla = new Map();
  for (const x of lista) {
    if (!esObjeto(x) || typeof x.id !== "string" || typeof x.vendor !== "string") continue;
    agregar(tabla, x.id, {
      entrada: x.input as number, salida: x.output as number, cache: x.input_cached as number | null,
      proveedor: x.vendor, nombreProveedor: x.vendor, fabricante: true, enlace: null,
    });
  }
  return tabla;
}

/** Se consultan en este orden hasta encontrar cada modelo. */
export const FUENTES: Fuente[] = [
  {
    nombre: "genai-prices",
    url: "https://raw.githubusercontent.com/pydantic/genai-prices/main/prices/data_slim.json",
    enlace: "https://github.com/pydantic/genai-prices",
    leer: leerGenaiPrices,
  },
  {
    nombre: "llm-prices",
    url: "https://www.llm-prices.com/current-v1.json",
    enlace: "https://www.llm-prices.com/",
    leer: leerLlmPrices,
  },
];

// ---------------------------------------------------------------- búsqueda

/** "gpt-5.4-mini-2026-03-17" y "claude-sonnet-4-5-20250929" sin la fecha del final. */
export const sinFecha = (nombre: string): string => nombre.replace(/-(?:\d{4}-\d{2}-\d{2}|\d{8})$/, "");

export interface Precio {
  entrada: number;
  salida: number;
  /** La entrada en caché; null si la fuente no la trae (o la trae distinta según el proveedor). */
  cache: number | null;
  /** De quién es el precio ("OpenAI"; si cobran lo mismo, varios separados por coma). */
  proveedor: string;
  enlace: string | null;
  /** El nombre con que se encontró, si no es el pedido (sin fecha o sin prefijo). */
  como: string | null;
}

export type Busqueda = { precio: Precio } | { aviso: string } | null;

export const proveedoresDe = (tabla: Tabla): Set<string> =>
  new Set([...tabla.values()].flat().map((o) => o.proveedor));

/** Entre varias ofertas del mismo modelo: si cobran distinto, no se elige callado. */
function elegir(ofertas: Oferta[], nombre: string, pedido: string): Busqueda {
  const distintos = new Map(ofertas.map((o) => [`${o.entrada}/${o.salida}`, o]));
  if (distintos.size > 1) {
    const cuales = [...distintos.values()].slice(0, 4).map((o) => `${o.nombreProveedor} ${o.entrada}/${o.salida}`);
    return { aviso: `${pedido}: la fuente lo trae con precios distintos según el proveedor (${cuales.join(", ")}). `
      + "Cárgalo a mano con el de quien te cobra." };
  }
  const o = ofertas[0];
  // La caché no decide la ambigüedad: si no coincide entre ellos, se sugiere sin caché y se cobra como entrada.
  const caches = new Set(ofertas.map((x) => x.cache));
  return { precio: {
    entrada: o.entrada, salida: o.salida, cache: caches.size === 1 ? o.cache : null,
    enlace: o.enlace, como: nombre === pedido ? null : nombre,
    proveedor: [...new Set(ofertas.map((x) => x.nombreProveedor))].join(", "),
  } };
}

/**
 * El precio de un modelo en una tabla. Primero el nombre exacto, después sin el
 * prefijo de proveedor y sin la fecha del final; nada más laxo, porque un
 * modelo distinto con un nombre parecido daría un precio equivocado.
 *
 * Si varios proveedores lo cobran, vale el que lo fabrica. Si el nombre traía
 * un proveedor conocido adelante ("openai/..."), vale ese. Si solo lo cobran
 * revendedores, uno solo o todos al mismo precio; si no, un aviso.
 */
export function buscar(modelo: string, tabla: Tabla, proveedores = proveedoresDe(tabla)): Busqueda {
  const barra = modelo.indexOf("/");
  const resto = barra > 0 ? modelo.slice(barra + 1) : modelo;
  const delPrefijo = barra > 0 && proveedores.has(modelo.slice(0, barra)) ? modelo.slice(0, barra) : "";
  let reventa: [Oferta[], string] | null = null;
  for (const nombre of new Set([modelo, resto, sinFecha(resto)])) {
    let ofertas = (tabla.get(nombre) || []).filter((o) => precioValido(o.entrada) && precioValido(o.salida));
    if (delPrefijo && nombre !== modelo) {
      ofertas = ofertas.filter((o) => o.proveedor === delPrefijo);
      if (ofertas.length) return elegir(ofertas, nombre, modelo);
      continue;
    }
    const propias = ofertas.filter((o) => o.fabricante);
    if (propias.length) return elegir(propias, nombre, modelo);
    if (ofertas.length && !reventa) reventa = [ofertas, nombre];
  }
  return reventa ? elegir(reventa[0], reventa[1], modelo) : null;
}

export interface Sugerencia extends Precio {
  modelo: string;
  fuente: string;
}

export interface Consultada {
  nombre: string;
  enlace: string;
  consultado: string;
}

export interface Respuesta {
  /** Uno por modelo pedido; null si ninguna fuente lo trae o la fuente lo trae a varios precios. */
  modelos: Record<string, Sugerencia | null>;
  /** Los que quedaron en null por traerse a varios precios, con su aviso. */
  dudas: Record<string, string>;
  /** La primera fuente que respondió, y cuándo se bajó. */
  fuente: string | null;
  consultado: string | null;
  fuentes: Consultada[];
  avisos: string[];
}

export type Traer = (f: Fuente) => Promise<{ datos: unknown; consultado: string }>;

/**
 * Busca cada modelo en las fuentes, en orden: la siguiente se baja solo si
 * quedó alguno sin precio. Una fuente caída o ilegible es un aviso, no un error.
 */
export async function sugerirPrecios(modelos: string[], traer: Traer, fuentes: Fuente[] = FUENTES,
  hoy = new Date().toISOString().slice(0, 10)): Promise<Respuesta> {
  const resultado: Record<string, Sugerencia | null> = Object.fromEntries(modelos.map((m) => [m, null]));
  const pendientes = new Set(modelos);
  const dudas = new Map<string, string>();
  const consultadas: Consultada[] = [];
  const avisos: string[] = [];
  for (const f of fuentes) {
    if (!pendientes.size) break;
    let tabla: Tabla;
    try {
      const { datos, consultado } = await traer(f);
      tabla = f.leer(datos, hoy);
      consultadas.push({ nombre: f.nombre, enlace: f.enlace, consultado });
    } catch (e) {
      avisos.push(`No pude consultar ${f.nombre}: ${(e as Error).message}.`);
      continue;
    }
    const proveedores = proveedoresDe(tabla);
    for (const m of [...pendientes]) {
      const r = buscar(m, tabla, proveedores);
      if (r && "precio" in r) {
        resultado[m] = { modelo: m, ...r.precio, fuente: f.nombre };
        pendientes.delete(m);
        dudas.delete(m);
      } else if (r && !dudas.has(m)) {
        dudas.set(m, `${r.aviso} (según ${f.nombre})`);
      }
    }
  }
  return {
    modelos: resultado, fuente: consultadas[0]?.nombre ?? null, consultado: consultadas[0]?.consultado ?? null,
    fuentes: consultadas, avisos: [...avisos, ...dudas.values()], dudas: Object.fromEntries(dudas),
  };
}

// ---------------------------------------------------------------- bajar una fuente

const UN_DIA = 86_400_000;
// En *.workers.dev la Cache API no guarda nada; lo que queda en memoria del
// isolate sí sirve ahí, aunque se pierde cuando Cloudflare lo recicla.
const enMemoria = new Map<string, { datos: unknown; consultado: string }>();
const vigente = (consultado: string) => Date.now() - Date.parse(consultado) < UN_DIA;

/**
 * Baja una fuente y la guarda un día: los precios no cambian de una hora a otra.
 * Solo la guarda si su lector la entiende.
 */
export async function traerFuente(f: Fuente): Promise<{ datos: unknown; consultado: string }> {
  const guardada = enMemoria.get(f.url);
  if (guardada && vigente(guardada.consultado)) return guardada;
  const cache = (globalThis as unknown as { caches?: { default?: Cache } }).caches?.default;
  const enCache = await cache?.match(f.url);
  const consultadoCache = enCache?.headers.get("x-consultado") || "";
  if (enCache && vigente(consultadoCache)) {
    const leida = { datos: await enCache.json(), consultado: consultadoCache };
    enMemoria.set(f.url, leida);
    return leida;
  }
  let r: Response;
  try {
    r = await fetch(f.url, { headers: { accept: "application/json" }, signal: AbortSignal.timeout(10_000) });
  } catch {
    throw new Error("no respondió");
  }
  if (!r.ok) throw new Error(`respondió ${r.status}`);
  const texto = await r.text();
  if (texto.length > 3_000_000) throw new Error("vino demasiado grande");
  // Se lee antes de guardarla: una respuesta que no es JSON, o que cambió de
  // forma, no queda un día en la caché. Si el lector lanza, su error es el aviso.
  let datos: unknown;
  try { datos = JSON.parse(texto); } catch { throw new Error("no vino en JSON"); }
  f.leer(datos, new Date().toISOString().slice(0, 10));
  const consultado = new Date().toISOString();
  await cache?.put(f.url, new Response(texto, { headers: {
    "content-type": "application/json", "cache-control": "max-age=86400", "x-consultado": consultado,
  } }));
  enMemoria.set(f.url, { datos, consultado });
  return { datos, consultado };
}
