// Prueba «Traer precios» sin red: la lectura de las fuentes y la búsqueda del
// Worker (src/precios.ts) y lo que la página hace con cada fila
// (public/precios.js). Las fuentes son copias recortadas de genai-prices y
// llm-prices bajadas el 02/11/2026, con los mismos campos y valores. La corre
// pruebas/web.py.
const W = await import(new URL("../src/precios.ts", import.meta.url));
const P = await import(new URL("../public/precios.js", import.meta.url));

let fallas = 0;
const check = (nombre, ok, detalle = "") => {
  if (!ok) fallas++;
  console.log(`${ok ? "OK" : "FALLA"}\t${nombre}${ok || !detalle ? "" : ` → ${detalle}`}`);
};
const HOY = "2026-11-02";

// ---------------------------------------------------------------- fuentes recortadas
const precios = (entrada, salida) => ({ input_mtok: entrada, output_mtok: salida });
const iguales = (...ns) => ({ or: ns.map((equals) => ({ equals })) });
const GENAI = [
  { id: "anthropic", name: "Anthropic", pricing_urls: ["https://www.anthropic.com/pricing#api"], model_match: { contains: "claude" },
    models: [
      { id: "claude-haiku-4-5", match: { or: [{ starts_with: "claude-haiku-4-5" }, { starts_with: "claude-haiku-4.5" }] },
        prices: { input_mtok: 1, cache_write_mtok: 1.25, cache_read_mtok: 0.1, output_mtok: 5 } },
      { id: "claude-opus-4-6", match: { or: [{ starts_with: "claude-opus-4-6" }, { starts_with: "claude-opus-4.6" }] },
        prices: [
          { prices: { input_mtok: { base: 5, tiers: [{ start: 200000, price: 10 }] }, output_mtok: { base: 25, tiers: [{ start: 200000, price: 37.5 }] } } },
          { constraint: { start_date: "2026-03-13" }, prices: { input_mtok: 5, cache_read_mtok: 0.5, output_mtok: 25 } }] },
      { id: "claude-sonnet-4-5", match: { or: [{ starts_with: "claude-sonnet-4-5" }, { starts_with: "claude-sonnet-4.5" }] },
        prices: { input_mtok: { base: 3, tiers: [{ start: 200000, price: 6 }] }, cache_read_mtok: { base: 0.3, tiers: [{ start: 200000, price: 0.6 }] },
          output_mtok: { base: 15, tiers: [{ start: 200000, price: 22.5 }] } } },
    ] },
  { id: "azure", name: "Microsoft Azure", pricing_urls: ["https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/#pricing"],
    models: [{ id: "phi-4-reasoning-plus", match: { equals: "phi-4-reasoning-plus" }, prices: precios(0.07, 0.35) }] },
  { id: "cerebras", name: "Cerebras", pricing_urls: ["https://www.cerebras.ai/pricing#pricing"], model_match: { contains: "cerebras" },
    models: [{ id: "gpt-oss-120b", match: { or: [{ equals: "gpt-oss-120b" }, { starts_with: "cerebras/gpt-oss-120b" }] }, prices: precios(0.35, 0.75) }] },
  { id: "deepseek", name: "Deepseek", pricing_urls: ["https://api-docs.deepseek.com/quick_start/pricing"], model_match: { contains: "deepseek" },
    models: [{ id: "deepseek-chat", match: { or: [{ starts_with: "deepseek-chat" }, { equals: "deepseek-chat-v3-0324" }] },
      prices: [{ prices: { input_mtok: 0.135, cache_read_mtok: 0.035, output_mtok: 0.55 } },
        { constraint: { start_time: "00:30:00Z", end_time: "16:30:00Z" }, prices: { input_mtok: 0.27, cache_read_mtok: 0.07, output_mtok: 1.1 } }] }] },
  { id: "google", name: "Google", pricing_urls: ["https://ai.google.dev/gemini-api/docs/pricing"], model_match: { contains: "gemini" },
    models: [
      { id: "claude-opus-4-6", match: { or: [{ contains: "claude-4-6-opus" }, { contains: "claude-opus-4-6" }] },
        prices: { input_mtok: { base: 5, tiers: [{ start: 200000, price: 10 }] }, output_mtok: { base: 25, tiers: [{ start: 200000, price: 37.5 }] } } },
      { id: "gemini-2.5-flash", match: iguales("gemini-2.5-flash", "gemini-2.5-flash-latest", "gemini-2.5-flash-preview-09-2025"),
        prices: { input_mtok: 0.3, cache_read_mtok: 0.03, output_mtok: 2.5, input_audio_mtok: 1 } },
    ] },
  { id: "groq", name: "Groq", pricing_urls: ["https://groq.com/pricing/"],
    models: [{ id: "llama-3.3-70b-versatile", match: { equals: "llama-3.3-70b-versatile" }, prices: precios(0.59, 0.79) }] },
  { id: "openai", name: "OpenAI", pricing_urls: ["https://developers.openai.com/api/docs/pricing"],
    model_match: { or: [{ starts_with: "gpt-" }, { regex: "^o[134]" }] },
    models: [
      { id: "gpt-4o", match: iguales("gpt-4o", "gpt-4o-2024-05-13", "gpt-4o-2024-08-06", "gpt-4o-2024-11-20"), prices: { input_mtok: 2.5, cache_read_mtok: 1.25, output_mtok: 10 } },
      { id: "gpt-4o-mini", match: iguales("gpt-4o-mini", "gpt-4o-mini-2024-07-18"), prices: { input_mtok: 0.15, cache_read_mtok: 0.075, output_mtok: 0.6 } },
      { id: "gpt-5-mini", match: iguales("gpt-5-mini", "gpt-5-mini-2025-08-07"), prices: { input_mtok: 0.25, cache_read_mtok: 0.025, output_mtok: 2 } },
      { id: "gpt-5.4", match: iguales("gpt-5.4", "gpt-5.4-2026-03-05", "gpt-5-4", "gpt-5-4-2026-03-05"),
        prices: { input_mtok: { base: 2.5, tiers: [{ start: 272000, price: 5 }] }, output_mtok: { base: 15, tiers: [{ start: 272000, price: 22.5 }] } } },
      { id: "gpt-5.4-mini", match: iguales("gpt-5.4-mini", "gpt-5.4-mini-2026-03-17", "gpt-5-4-mini", "gpt-5-4-mini-2026-03-17"),
        prices: { input_mtok: 0.75, cache_read_mtok: 0.075, output_mtok: 4.5 } },
      { id: "gpt-5.4-nano", match: iguales("gpt-5.4-nano", "gpt-5.4-nano-2026-03-17", "gpt-5-4-nano", "gpt-5-4-nano-2026-03-17"),
        prices: { input_mtok: 0.2, cache_read_mtok: 0.02, output_mtok: 1.25 } },
      { id: "gpt-5.5", match: iguales("gpt-5.5", "gpt-5.5-2026-04-23", "gpt-5-5"), prices: { input_mtok: 5, cache_read_mtok: 0.5, output_mtok: 30 } },
      { id: "gpt-oss-120b", match: { equals: "gpt-oss-120b" }, prices: precios(0.039, 0.18) },
      { id: "o3", match: iguales("o3", "o3-2025-04-16"), prices: [{ prices: { input_mtok: 10, cache_read_mtok: 0.5, output_mtok: 40 } },
        { constraint: { start_date: "2025-06-10" }, prices: { input_mtok: 2, cache_read_mtok: 0.5, output_mtok: 8 } }] },
      { id: "text-embedding-3-small", match: { equals: "text-embedding-3-small" }, prices: { input_mtok: 0.02 } },
    ] },
  { id: "openrouter", name: "OpenRouter", pricing_urls: ["https://openrouter.ai/models"],
    models: [
      { id: "openai/gpt-5.4-mini", match: { equals: "openai/gpt-5.4-mini" }, prices: { input_mtok: 0.75, cache_read_mtok: 0.075, output_mtok: 4.5 } },
      { id: "phi-4-reasoning-plus", match: { equals: "phi-4-reasoning-plus" }, prices: precios(0.07, 0.35) },
    ] },
  { id: "ovhcloud", name: "OVHcloud AI Endpoints", pricing_urls: ["https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/models"],
    models: [{ id: "gpt-oss-120b", match: { equals: "gpt-oss-120b" }, prices: precios(0.09, 0.47) }] },
];
const LLM = { updated_at: "2026-10-26", prices: [
  { id: "claude-sonnet-4.5", vendor: "anthropic", name: "Claude Sonnet 4.5 ≤200k", input: 3, output: 15, input_cached: 0.3 },
  { id: "deepseek-chat", vendor: "deepseek", name: "DeepSeek Chat", input: 0.27, output: 1.1, input_cached: null },
  { id: "gemini-2.5-flash", vendor: "google", name: "Gemini 2.5 Flash", input: 0.3, output: 2.5, input_cached: 0.03 },
  { id: "gpt-4o", vendor: "openai", name: "GPT-4o", input: 2.5, output: 10, input_cached: 1.25 },
  { id: "gpt-5.4-mini", vendor: "openai", name: "GPT-5.4 Mini", input: 0.75, output: 4.5, input_cached: 0.075 },
  { id: "gpt-5.5", vendor: "openai", name: "GPT-5.5 ≤272k", input: 5.0, output: 30.0, input_cached: 0.5 },
  { id: "grok-4-fast", vendor: "xai", name: "Grok 4 Fast", input: 0.2, output: 0.5, input_cached: 0.05 },
  { id: "grok-4-fast", vendor: "xai", name: "Grok 4 Fast ≤128k", input: 0.2, output: 0.5, input_cached: 0.05 },
] };

// ---------------------------------------------------------------- lectura y búsqueda
const tabla = W.leerGenaiPrices(GENAI, HOY);
const precio = (modelo, t = tabla) => W.buscar(modelo, t)?.precio ?? null;
const es = (p, e, s) => Boolean(p) && p.entrada === e && p.salida === s;
const ver = (x) => JSON.stringify(x);

const REFERENCIA = [["gpt-5.4-mini", 0.75, 4.5], ["gpt-5.5", 5, 30], ["gpt-5.4", 2.5, 15], ["gpt-5.4-nano", 0.2, 1.25],
  ["gpt-5-mini", 0.25, 2], ["gpt-4o-mini", 0.15, 0.6], ["gpt-4o", 2.5, 10]];
const malos = REFERENCIA.filter(([m, e, s]) => !es(precio(m), e, s) || precio(m).proveedor !== "OpenAI");
check("los 7 modelos de OpenAI del curso, con la tarifa estándar y de OpenAI", !malos.length, ver(malos));
check("el enlace es la página de precios del proveedor", precio("gpt-4o")?.enlace === "https://developers.openai.com/api/docs/pricing");
check("{ base, tiers } usa la base (gpt-5.4, claude-sonnet-4-5)", es(precio("gpt-5.4"), 2.5, 15) && es(precio("claude-sonnet-4-5"), 3, 15));
check("un modelo de Anthropic", es(precio("claude-haiku-4-5"), 1, 5) && precio("claude-haiku-4-5").proveedor === "Anthropic"
  && precio("claude-haiku-4-5").enlace === "https://www.anthropic.com/pricing#api");
check("un modelo de Google", es(precio("gemini-2.5-flash"), 0.3, 2.5) && precio("gemini-2.5-flash").proveedor === "Google");
check("un alias exacto de la fuente cuenta como exacto", es(precio("gpt-5.4-mini-2026-03-17"), 0.75, 4.5)
  && precio("gpt-5.4-mini-2026-03-17").como === null);
check("sin la fecha del final (AAAAMMDD)", es(precio("gpt-5.4-mini-20260317"), 0.75, 4.5) && precio("gpt-5.4-mini-20260317").como === "gpt-5.4-mini");
check("sin la fecha al estilo Anthropic", es(precio("claude-sonnet-4-5-20250929"), 3, 15)
  && precio("claude-sonnet-4-5-20250929").como === "claude-sonnet-4-5");
check("sin la fecha AAAA-MM-DD aunque la fuente no la tenga", es(precio("gpt-4o-mini-2099-01-01"), 0.15, 0.6));
check("nada más laxo: un nombre parecido no es el mismo modelo",
  ["gpt-5.4-mini-high", "gpt-4o-min", "claude-sonnet-4-5-extra", "gpt-5.4-mini-2026", "mini"].every((m) => W.buscar(m, tabla) === null));
check("un modelo local que la fuente no trae no tiene precio", W.buscar("llama-local:8b", tabla) === null);
check("un nombre como __proto__ no rompe la búsqueda", W.buscar("__proto__", tabla) === null);
check("con prefijo del fabricante: el precio es del fabricante, no del revendedor",
  es(precio("openai/gpt-5.4-mini"), 0.75, 4.5) && precio("openai/gpt-5.4-mini").proveedor === "OpenAI");
check("con prefijo de Anthropic", precio("anthropic/claude-haiku-4-5")?.proveedor === "Anthropic");
check("con prefijo de un revendedor: el de ese revendedor", precio("openrouter/openai/gpt-5.4-mini")?.proveedor === "OpenRouter");
check("con prefijo y fecha a la vez", es(precio("openai/gpt-5.4-mini-20260317"), 0.75, 4.5));
check("id repetido en Anthropic y Google (Vertex): vale Anthropic, que lo fabrica",
  es(precio("claude-opus-4-6"), 5, 25) && precio("claude-opus-4-6").proveedor === "Anthropic");
check("id repetido con precios distintos: vale el del fabricante",
  es(precio("gpt-oss-120b"), 0.039, 0.18) && precio("gpt-oss-120b").proveedor === "OpenAI");
const sinOpenai = W.leerGenaiPrices(GENAI.filter((p) => p.id !== "openai"), HOY);
const duda = W.buscar("gpt-oss-120b", sinOpenai);
check("solo revendedores con precios distintos: aviso, no se elige callado",
  duda && "aviso" in duda && duda.aviso.includes("Cerebras") && duda.aviso.includes("OVHcloud"), ver(duda));
check("solo revendedores al mismo precio: se usa y se nombran los dos",
  es(precio("phi-4-reasoning-plus"), 0.07, 0.35) && precio("phi-4-reasoning-plus").proveedor === "Microsoft Azure, OpenRouter");
check("solo un revendedor: se usa y se dice cuál", precio("llama-3.3-70b-versatile")?.proveedor === "Groq");
check("precio con fecha de inicio: vale el que ya empezó", es(precio("o3"), 2, 8)
  && es(precio("o3", W.leerGenaiPrices(GENAI, "2025-01-01")), 10, 40));
check("precio que cambia según la hora: no se sugiere", W.buscar("deepseek-chat", tabla) === null);
check("sin precio de salida (embeddings) no se sugiere", W.buscar("text-embedding-3-small", tabla) === null);

const RAROS = [{ id: "raro", name: "Raro", pricing_urls: ["javascript:alert(1)"], model_match: { contains: "x" }, models: [
  { id: "x-negativo", match: { equals: "x-negativo" }, prices: precios(-1, 2) },
  { id: "x-enorme", match: { equals: "x-enorme" }, prices: precios(1, 1e9) },
  { id: "x-texto", match: { equals: "x-texto" }, prices: precios("0.5", 2) },
  { id: "x-nulo", match: { equals: "x-nulo" }, prices: precios(null, 2) },
  { id: "x-tramos-rotos", match: { equals: "x-tramos-rotos" }, prices: precios({ tiers: [] }, 2) },
  { id: "x-bien", match: { equals: "x-bien" }, prices: precios(0, 9999) },
  { id: "x-regex-rota", match: { regex: "(" }, prices: precios(1, 2) },
] }, "basura", null, { id: 3 }];
const raros = W.leerGenaiPrices(RAROS, HOY);
check("descarta negativos, enormes, texto, nulos y tramos sin base",
  ["x-negativo", "x-enorme", "x-texto", "x-nulo", "x-tramos-rotos"].every((m) => W.buscar(m, raros) === null));
check("0 y 9999 sí valen (el rango de PRECIOS_API)", es(precio("x-bien", raros), 0, 9999));
check("un enlace que no es https no pasa", precio("x-bien", raros)?.enlace === null);
check("una regex rota de la fuente no rompe la lectura", W.buscar("x-regex-rota", raros) === null);
const DECIMALES = [{ id: "cohere", name: "Cohere", model_match: { contains: "command" }, models: [
  { id: "command-r7b", match: { equals: "command-r7b" }, prices: precios(0.0375, 0.15) },
  { id: "command-ruido", match: { equals: "command-ruido" }, prices: precios(0.18000000000000002, 0.6000000000000001) },
] }];
const decimales = W.leerGenaiPrices(DECIMALES, HOY);
check("cuatro decimales llegan tal cual (0.0375)", es(precio("command-r7b", decimales), 0.0375, 0.15));
check("el ruido de coma flotante de la fuente se limpia (0.18000000000000002 -> 0.18)",
  es(precio("command-ruido", decimales), 0.18, 0.6), ver(precio("command-ruido", decimales)));
let lanza = "";
try { W.leerGenaiPrices({ no: "lista" }, HOY); } catch (e) { lanza = e.message; }
check("una fuente con otra forma se reconoce", lanza === "no trae la lista de proveedores");

const llm = W.leerLlmPrices(LLM);
check("llm-prices: vendor es quien fabrica", es(precio("gpt-5.4-mini", llm), 0.75, 4.5) && precio("gpt-5.4-mini", llm).proveedor === "openai");
check("llm-prices: sin página de precios del proveedor", precio("gpt-4o", llm)?.enlace === null);
check("llm-prices: un id repetido al mismo precio no es ambiguo", es(precio("grok-4-fast", llm), 0.2, 0.5));
check("llm-prices: con prefijo de proveedor", es(precio("google/gemini-2.5-flash", llm), 0.3, 2.5));

check("nombres de modelo válidos", ["gpt-5.4-mini", "openai/gpt-5.4-mini", "openrouter/openai/gpt-4o", "claude-sonnet-4-5-20250929",
  "llama3.1:8b", "o3"].every((m) => W.NOMBRE_MODELO.test(m)));
check("nombres de modelo inválidos", ["", "a", "/gpt", "gpt/", "a//b", "a b", "<b>", "../x", "a/b/c/d", "x".repeat(61)]
  .every((m) => !W.NOMBRE_MODELO.test(m)));

// ---------------------------------------------------------------- varias fuentes
const fuentes = [
  { nombre: "genai-prices", url: "https://genai.invalid", enlace: "https://github.com/pydantic/genai-prices", leer: W.leerGenaiPrices },
  { nombre: "llm-prices", url: "https://llm.invalid", enlace: "https://www.llm-prices.com/", leer: W.leerLlmPrices },
];
const traerCon = (datos, pedidas = []) => async (f) => {
  pedidas.push(f.nombre);
  const d = datos[f.nombre];
  if (d instanceof Error) throw d;
  return { datos: d, consultado: "2026-11-02T12:00:00.000Z" };
};
let pedidas = [];
let r = await W.sugerirPrecios(["gpt-5.4-mini", "claude-haiku-4-5"], traerCon({ "genai-prices": GENAI, "llm-prices": LLM }, pedidas), fuentes, HOY);
check("si la principal trae todo, la de respaldo no se baja", ver(pedidas) === '["genai-prices"]'
  && r.modelos["gpt-5.4-mini"]?.fuente === "genai-prices" && r.fuente === "genai-prices" && r.consultado === "2026-11-02T12:00:00.000Z");
pedidas = [];
r = await W.sugerirPrecios(["gpt-5.4-mini", "deepseek-chat", "mi-modelo-local"], traerCon({ "genai-prices": GENAI, "llm-prices": LLM }, pedidas), fuentes, HOY);
check("lo que falta se busca en la de respaldo", ver(pedidas) === '["genai-prices","llm-prices"]'
  && r.modelos["deepseek-chat"]?.fuente === "llm-prices" && es(r.modelos["deepseek-chat"], 0.27, 1.1));
check("un modelo que ninguna trae queda en null", r.modelos["mi-modelo-local"] === null && r.fuentes.length === 2);
r = await W.sugerirPrecios(["gpt-5.4-mini", "gpt-oss-120b"], traerCon({ "genai-prices": new Error("respondió 503"), "llm-prices": LLM }), fuentes, HOY);
check("fuente principal caída: aviso y se usa la de respaldo", r.avisos[0] === "No pude consultar genai-prices: respondió 503."
  && r.fuente === "llm-prices" && r.modelos["gpt-5.4-mini"]?.fuente === "llm-prices" && r.modelos["gpt-oss-120b"] === null, ver(r));
r = await W.sugerirPrecios(["gpt-4o"], traerCon({ "genai-prices": new Error("no respondió"), "llm-prices": new Error("respondió 500") }), fuentes, HOY);
check("las dos caídas: dos avisos, nada sugerido", r.avisos.length === 2 && r.modelos["gpt-4o"] === null && r.fuente === null && !r.fuentes.length);
r = await W.sugerirPrecios(["gpt-4o"], traerCon({ "genai-prices": { cambió: "de forma" }, "llm-prices": LLM }), fuentes, HOY);
check("una fuente que cambió de forma es un aviso, no un error", r.avisos[0].includes("no trae la lista de proveedores")
  && r.modelos["gpt-4o"]?.fuente === "llm-prices");
r = await W.sugerirPrecios(["gpt-oss-120b"], traerCon({ "genai-prices": GENAI.filter((p) => p.id !== "openai"), "llm-prices": LLM }), fuentes, HOY);
check("la ambigüedad llega como aviso, con la fuente", r.modelos["gpt-oss-120b"] === null && r.avisos.some((a) => a.includes("según genai-prices")));
check("y en dudas, para que la fila no diga que la fuente no lo trae", r.dudas["gpt-oss-120b"]?.includes("Cerebras"), ver(r.dudas));
r = await W.sugerirPrecios(["gpt-oss-120b"], traerCon({ "genai-prices": GENAI.filter((p) => p.id !== "openai"), "llm-prices": {
  prices: [{ id: "gpt-oss-120b", vendor: "openai", input: 0.1, output: 0.5 }] } }), fuentes, HOY);
check("si la de respaldo lo trae a un solo precio, deja de ser duda", es(r.modelos["gpt-oss-120b"], 0.1, 0.5)
  && !("gpt-oss-120b" in r.dudas), ver(r));
// traerFuente con un fetch falso: lo que el lector no entiende no se guarda (aquí no hay Cache API, solo memoria).
let bajadas = 0;
const fetchReal = globalThis.fetch;
globalThis.fetch = async () => { bajadas++; return new Response(JSON.stringify({ cambió: "de forma" })); };
const rara = { ...fuentes[0], url: "https://rara.invalid/precios.json" };
const errores = [];
for (let i = 0; i < 2; i++) { try { await W.traerFuente(rara); } catch (e) { errores.push(e.message); } }
globalThis.fetch = fetchReal;
check("una fuente con otra forma no queda guardada: se vuelve a bajar", bajadas === 2
  && errores.every((e) => e === "no trae la lista de proveedores"), ver({ bajadas, errores }));
check("FUENTES: genai-prices primero y llm-prices de respaldo", W.FUENTES.map((f) => f.nombre).join() === "genai-prices,llm-prices"
  && W.FUENTES.every((f) => f.url.startsWith("https://") && f.enlace.startsWith("https://") && typeof f.leer === "function"));

// ---------------------------------------------------------------- la página, fila por fila
const sug = { entrada: 0.75, salida: 4.5, proveedor: "OpenAI", enlace: "https://developers.openai.com/api/docs/pricing", como: null };
const vacia = { entrada: "", salida: "" };
let d = P.decidirFila(vacia, undefined, sug);
check("fila vacía: se llena", d.accion === "llenar" && d.entrada === "0.75" && d.salida === "4.5" && d.revisar === null, ver(d));
d = P.decidirFila({ entrada: "0.8", salida: "4.5" }, [0.8, 4.5], sug);
check("un valor manual distinto no se pisa: se ofrece «Usar»", d.accion === "distinta" && d.entrada === undefined && d.salida === undefined, ver(d));
d = P.decidirFila({ entrada: "0.8", salida: "" }, undefined, sug);
check("fila a medias con otro valor: no se toca ni la vacía", d.accion === "distinta", ver(d));
d = P.decidirFila({ entrada: "0.75", salida: "" }, undefined, sug);
check("fila a medias que coincide: se completa la vacía", d.accion === "llenar" && d.entrada === "0.75" && d.salida === "4.5", ver(d));
check("fila con el mismo precio: igual", P.decidirFila({ entrada: "0.75", salida: "4.50" }, [0.75, 4.5], sug).accion === "igual");
check("sin sugerencia: la fila queda como está", P.decidirFila({ entrada: "1", salida: "" }, undefined, null).accion === "sin-dato");
check("con varios precios en la fuente: ambiguo, no sin dato",
  P.decidirFila(vacia, undefined, null, "gpt-oss-120b: la fuente lo trae con precios distintos").accion === "ambiguo");
d = P.decidirFila(vacia, undefined, { ...sug, entrada: 0.0375, salida: 0.15 });
check("cuatro decimales se escriben enteros en la celda", d.entrada === "0.0375" && d.salida === "0.15", ver(d));
d = P.decidirFila(vacia, undefined, { ...sug, entrada: 0.18000000000000002, salida: 0.6000000000000001 });
check("sin ruido de coma flotante en la celda", d.entrada === "0.18" && d.salida === "0.6", ver(d));
check("«Usar» escribe lo mismo", P.comoCelda(0.18000000000000002) === "0.18" && P.comoCelda(0.0375) === "0.0375" && P.comoCelda(5) === "5");
check("el nombre de modelo de la página es el del Worker", P.NOMBRE_MODELO.source === W.NOMBRE_MODELO.source);
check("una sugerencia inválida no se usa", [NaN, -1, 1e6, "0.5", null].every((x) =>
  P.decidirFila(vacia, undefined, { ...sug, entrada: x }).accion === "sin-dato"));
check("entrada más cara que la salida: para revisar", P.decidirFila(vacia, undefined, { ...sug, entrada: 5, salida: 2 }).revisar?.includes("entrada"));
check("más de 10 veces distinto de lo guardado: para revisar",
  P.decidirFila({ entrada: "8", salida: "46" }, [8, 46], sug).revisar?.includes("10 veces")
  && P.decidirFila({ entrada: "0.07", salida: "4.5" }, [0.07, 4.5], sug).revisar?.includes("10 veces"));
check("justo 10 veces todavía no se marca", P.decidirFila({ entrada: "7.5", salida: "45" }, [7.5, 45], sug).revisar === null);
check("dentro de 10 veces no se marca", P.decidirFila({ entrada: "0.5", salida: "4" }, [0.5, 4], sug).revisar === null);
check("guardado en 0 y sugerido distinto: para revisar", P.decidirFila({ entrada: "0", salida: "0" }, [0, 0], sug).revisar !== null);
check("el resumen cuenta cada caso", P.resumenDecisiones([{ accion: "llenar" }, { accion: "llenar", revisar: "x" }, { accion: "distinta" },
  { accion: "sin-dato" }]) === "Se llenaron 2 modelos; 1 tiene otro precio (pulsa «Usar» si corresponde); 1 sin dato en la fuente; 1 para revisar.",
  P.resumenDecisiones([{ accion: "llenar" }, { accion: "llenar", revisar: "x" }, { accion: "distinta" }, { accion: "sin-dato" }]));
check("el resumen en singular", P.resumenDecisiones([{ accion: "llenar" }, { accion: "ambiguo" }])
  === "Se llenó 1 modelo; 1 con varios precios en la fuente.", P.resumenDecisiones([{ accion: "llenar" }, { accion: "ambiguo" }]));
// La caché: la fuente la trae para casi todo modelo de OpenAI y Anthropic.
const conCache = { ...sug, cache: 0.075 };
d = P.decidirFila({ entrada: "0.75", salida: "4.5" }, [0.75, 4.5], conCache);
check("fila igual y fuente con caché, sin celda de caché: igual (no un falso «llenar»)", d.accion === "igual", ver(d));
check("y el resumen no dice que se llenó", P.resumenDecisiones([d]) === "1 ya tenía ese precio.", P.resumenDecisiones([d]));
d = P.decidirFila({ entrada: "0.75", salida: "4.5", cache: "" }, [0.75, 4.5], conCache);
check("fila igual con la caché vacía: se llena solo la caché", d.accion === "llenar" && d.cache === "0.075"
  && d.entrada === "0.75" && d.salida === "4.5", ver(d));
d = P.decidirFila({ entrada: "0.75", salida: "4.5", cache: "0.075" }, [0.75, 4.5, 0.075], conCache);
check("fila igual con la misma caché: igual", d.accion === "igual", ver(d));
d = P.decidirFila({ entrada: "0.75", salida: "4.5", cache: "0.1" }, [0.75, 4.5, 0.1], conCache);
check("otra caché escrita no se pisa: se ofrece «Usar»", d.accion === "distinta", ver(d));
d = P.decidirFila({ entrada: "", salida: "", cache: "0.1" }, undefined, sug);
check("sin caché en la fuente, la celda escrita no cuenta", d.accion === "llenar" && !("cache" in d), ver(d));
check("caché más cara que la entrada: para revisar",
  P.decidirFila({ entrada: "", salida: "", cache: "" }, undefined, { ...sug, cache: 1 }).revisar?.includes("caché"));
check("el texto de la sugerencia trae la caché", P.textoPrecio(conCache) === "0.75 / 4.5 / caché 0.075", P.textoPrecio(conCache));
check("PRECIOS_API acepta [entrada, salida] y [entrada, salida, caché]",
  W.preciosValidos('{"a-1": [0.75, 4.5]}') && W.preciosValidos('{"a-1": [0.75, 4.5, 0.075]}'));
check("y rechaza cuatro valores, uno solo o una caché negativa", !W.preciosValidos('{"a-1": [1, 2, 3, 4]}')
  && !W.preciosValidos('{"a-1": [1]}') && !W.preciosValidos('{"a-1": [1, 2, -0.1]}'));
r = await W.sugerirPrecios(["gpt-5.4-mini", "gpt-oss-120b"], traerCon({ "genai-prices": GENAI }), fuentes, HOY);
check("sugerirPrecios trae la caché cuando la fuente la tiene, y null si no", r.modelos["gpt-5.4-mini"]?.cache === 0.075
  && (r.modelos["gpt-oss-120b"] ?? { cache: null }).cache === null, ver(r.modelos));

check("de dónde salió, con el nombre con que se encontró", P.textoOrigen({ ...sug, como: "gpt-5.4-mini" }) === "OpenAI, como gpt-5.4-mini"
  && P.textoOrigen(sug) === "OpenAI" && P.textoPrecio(sug) === "0.75 / 4.5");
check("solo enlaces https", P.enlaceSeguro("javascript:alert(1)") === null && P.enlaceSeguro(sug.enlace) === sug.enlace
  && P.enlaceSeguro(null) === null);
check("la fecha de consulta", P.fechaConsulta("2026-11-02T12:00:00.000Z") === "02-11-2026" && P.fechaConsulta("x") === "",
  P.fechaConsulta("2026-11-02T12:00:00.000Z"));

console.log(fallas ? `${fallas} fallas` : "todo OK");
process.exit(fallas ? 1 : 0);
