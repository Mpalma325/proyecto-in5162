// Configuración › La IA › Probar criterio.
//
// Reevalúa respuestas ya corregidas con un prompt candidato (el trabajo
// tests.experimento, modulos/tests/experimento.py) y muestra, respuesta por
// respuesta, la nota y la originalidad de antes y de después, con las dos
// correcciones lado a lado. No manda correos ni cambia notas ni el prompt del
// semestre: lo único que gasta es API, y antes de correr dice cuánto.

import {
  api, caja, el, evaluacionDeTexto, historialTrabajos, pedirTrabajo, preciosApi, respuestaLegible, seguirTrabajo,
  vistaCorreo,
} from "./comun.js";
import { leerConsumo, textoConsumo } from "./consumo.js";
import {
  NIVELES, consumoPorRespuesta, estimarCosto, huella, ordenarPorCambio, rangos, resumirComparacion,
  semanasPorVersion, textoNota,
} from "./criterio.js";
import { leerCsv } from "./csv.js";

const VIGENTE = "tests_semanales/prompts/evaluar_respuesta.md";
const USADOS = /^tests_semanales\/prompts_usados\/evaluar_respuesta@([0-9a-f]{8})\.md$/;
// El tope del motor (motor/trabajo.py, _experimento).
const MAXIMO = 300;

const urlArchivo = (semestre, ruta) =>
  `/api/archivo/${encodeURIComponent(semestre)}/${ruta.split("/").map(encodeURIComponent).join("/")}`;

async function leerTexto(semestre, ruta) {
  const r = await fetch(urlArchivo(semestre, ruta), { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.text();
}

/** Las filas de un CSV como objetos {columna: valor}. */
function objetosCsv(texto) {
  const { columnas, filas } = leerCsv(texto);
  return filas.map((f) => Object.fromEntries(columnas.map((c, i) => [c, f[i] ?? ""])));
}

/** Una corrección del modelo, para dibujarla como correo: HTML tal cual, texto rearmado. */
function cuerpoCorreccion(texto) {
  const limpio = String(texto || "").trim().replace(/^```(?:html)?\s*/, "").replace(/\s*```$/, "");
  return /<(p|b|strong|br|div|ul|li|h\d)\b/i.test(limpio) ? limpio : evaluacionDeTexto(limpio);
}

// ---------------------------------------------------------------- la comparación

function flecha(antes, despues) {
  if (antes === despues) return el("span", { class: "tenue" }, "=");
  return el("span", { class: "tenue" }, "→");
}

function delta(d) {
  const x = Number(String(d).replace(",", "."));
  if (String(d).trim() === "" || Number.isNaN(x) || x === 0) return null;
  return el("span", { class: x > 0 ? "delta sube" : "delta baja" },
    `${x > 0 ? "+" : ""}${x.toLocaleString("es-CL", { maximumFractionDigits: 2 })}`);
}

/** Una respuesta reevaluada: plegada, la línea con el cambio; abierta, las dos correcciones. */
function filaComparacion(f) {
  const cuerpo = el("div", { class: "detalle-comparacion" });
  const d = el("details", { class: "fila-comparacion" },
    el("summary", {},
      el("span", { class: "quien" }, f.Nombre || f.Correo, el("span", { class: "tenue" }, ` · semana ${f.Semana}`)),
      el("span", { class: "cambio" }, "Nota ", textoNota(f.NotaAntes), " ", flecha(f.NotaAntes, f.NotaDespues), " ",
        f.FormatoOK === "NO" ? el("strong", { class: "aviso-texto" }, "sin nota legible") : textoNota(f.NotaDespues),
        " ", delta(f.DeltaNota)),
      el("span", { class: "cambio" }, "Originalidad ", f.OriginalidadAntes || "—", " ",
        flecha(f.OriginalidadAntes, f.OriginalidadDespues), " ", f.OriginalidadDespues || "—")),
    cuerpo);
  // Las correcciones se dibujan al abrir: con cientos de filas, dos iframes por
  // fila desde el principio hacen la página lenta.
  d.addEventListener("toggle", () => {
    if (!d.open || cuerpo.childElementCount) return;
    cuerpo.append(
      el("h5", {}, "Lo que respondió"),
      el("div", { class: "respuesta" }, respuestaLegible(f.Respuesta)),
      el("div", { class: "dos-columnas" },
        el("div", {}, el("h5", {}, "La corrección que recibió"),
          f.EvaluacionAntes ? vistaCorreo({ cuerpo: cuerpoCorreccion(f.EvaluacionAntes), html: true })
            : el("p", { class: "tenue" }, "Esta prueba es anterior a guardar la corrección original.")),
        el("div", {}, el("h5", {}, "Con el prompt candidato"),
          vistaCorreo({ cuerpo: cuerpoCorreccion(f.EvaluacionNueva), html: true }))));
  });
  return d;
}

function resumen(filas) {
  const r = resumirComparacion(filas);
  const kpi = (etiqueta, valor, pie) => el("div", { class: "kpi" },
    el("div", { class: "etiqueta" }, etiqueta), el("div", { class: "valor" }, valor), pie ? el("div", { class: "tenue" }, pie) : null);
  const media = (x) => (x === null ? "—" : x.toLocaleString("es-CL", { maximumFractionDigits: 2 }));
  const niveles = NIVELES.filter((n) => r.antes[n] || r.despues[n]);
  return [
    el("div", { class: "kpis k4" },
      kpi("Respuestas", String(r.total), r.sinFormato ? `${r.sinFormato} sin nota legible` : "todas con nota legible"),
      kpi("Nota media", `${media(r.mediaAntes)} → ${media(r.mediaDespues)}`, "antes → con el candidato"),
      kpi("Notas", `${r.notas.suben} ↑  ${r.notas.bajan} ↓`, `${r.notas.iguales} iguales`),
      kpi("Originalidad", `${r.originalidad.suben} ↑  ${r.originalidad.bajan} ↓`, `${r.originalidad.iguales} iguales`)),
    niveles.length ? el("div", { class: "tabla-envoltura" }, el("table", { class: "tabla-originalidad" },
      el("thead", {}, el("tr", {}, el("th", {}, "Originalidad"), niveles.map((n) => el("th", {}, n)))),
      el("tbody", {},
        el("tr", {}, el("th", {}, "Antes"), niveles.map((n) => el("td", {}, String(r.antes[n])))),
        el("tr", {}, el("th", {}, "Con el candidato"), niveles.map((n) => el("td", {}, String(r.despues[n]))))))) : null,
  ];
}

/** Debajo de una prueba terminada: el resumen, cada respuesta y la descarga del CSV. */
function comparacion(semestre, ruta) {
  const nodo = el("div", { class: "comparacion" }, el("p", { class: "cargando" }, "Cargando la comparación…"));
  leerTexto(semestre, ruta).then((texto) => {
    const filas = objetosCsv(texto);
    if (!filas.length) { nodo.replaceChildren(caja("info", "La prueba no reevaluó ninguna respuesta.")); return; }
    nodo.replaceChildren(
      el("h4", {}, "Antes y con el prompt candidato"),
      ...resumen(filas).filter(Boolean),
      el("p", { class: "tenue" }, "Primero las que más cambiaron. Abre una para leer las dos correcciones."),
      el("div", { class: "lista-comparacion" }, ordenarPorCambio(filas).map(filaComparacion)),
      el("a", { class: "descarga", href: `${urlArchivo(semestre, ruta)}?descargar` }, `Descargar ${ruta.split("/").pop()}`));
  }).catch((e) => nodo.replaceChildren(caja("aviso", `No pude leer el resultado (${e.message}).`)));
  return nodo;
}

// ---------------------------------------------------------------- la vista

export function vistaProbarCriterio({ semestre, archivos }) {
  const resultado = el("div", { id: "resultado-criterio" });
  const area = el("textarea", { class: "prompt", spellcheck: "false", disabled: true }, "Cargando el prompt vigente…");
  const origen = el("select", {}, el("option", { value: VIGENTE }, "El prompt vigente del semestre"));
  const n = el("input", { type: "number", min: "1", max: String(MAXIMO), step: "1", value: "20" });
  const todas = el("input", { type: "checkbox", checked: true });
  const semana = el("input", { type: "number", min: "1", max: "52", value: "1" });
  const campoSemana = el("label", { hidden: true }, "Semana", semana);
  const semilla = el("input", { type: "number", min: "0", max: "99999", value: "19",
    title: "La misma semilla elige las mismas respuestas: así dos prompts se comparan sobre la misma muestra." });
  const costo = el("p", { class: "costo-estimado" });
  const botonMuestra = el("button", { class: "secundario", type: "button" }, "Ver qué respuestas usaría");
  const botonProbar = el("button", { class: "primario", type: "button" }, "Probar el criterio");
  let vigente = "";
  let editado = false;
  let porRespuesta = null;
  let precios = {};

  const cargar = (texto) => { area.value = texto; area.disabled = false; editado = false; actualizar(); };

  // Desde qué versión partir: la vigente o cualquiera de las que corrigieron
  // de verdad (prompts_usados/), con las semanas en que se usó cada una.
  const versiones = archivos.map((a) => a.ruta.match(USADOS)).filter(Boolean).map((m) => ({ ruta: m[0], huella: m[1] }));
  let semanasDe = null; // { huella: [semanas] }, cuando llega el log
  let huellaVigente = "";
  const grupoVersiones = versiones.length ? el("optgroup", { label: "Versiones usadas en correcciones" }) : null;
  function pintarVersiones() {
    if (!grupoVersiones) return;
    const elegida = origen.value;
    grupoVersiones.replaceChildren(...versiones.map((v) => {
      const s = semanasDe?.[v.huella] || [];
      const cuando = !semanasDe ? "" : s.length ? ` · ${s.length === 1 ? "semana" : "semanas"} ${rangos(s)}`
        : " · sin correcciones registradas";
      return el("option", { value: v.ruta }, `Versión ${v.huella}${v.huella === huellaVigente ? " (la vigente)" : ""}${cuando}`);
    }));
    origen.value = elegida;
  }
  if (grupoVersiones) { origen.append(grupoVersiones); pintarVersiones(); }
  let elegidaAntes = origen.value;
  origen.addEventListener("change", async () => {
    if (editado && !confirm("Vas a reemplazar el prompt que estás editando. ¿Seguir?")) {
      origen.value = elegidaAntes;
      return;
    }
    elegidaAntes = origen.value;
    area.disabled = true;
    try { cargar(await leerTexto(semestre, origen.value)); } catch (e) {
      area.disabled = false;
      resultado.replaceChildren(caja("aviso", `No pude leer esa versión (${e.message}).`));
    }
  });
  area.addEventListener("input", () => { editado = true; actualizar(); });

  function actualizar() {
    semana.disabled = todas.checked;
    campoSemana.hidden = todas.checked;
    const cuantas = Number(n.value);
    const total = estimarCosto({ n: cuantas, porRespuesta, largoCandidato: area.value.length,
      largoVigente: vigente.length, precios });
    if (!(cuantas >= 1 && cuantas <= MAXIMO)) {
      costo.replaceChildren(caja("aviso", `Entre 1 y ${MAXIMO} respuestas.`));
    } else if (!total) {
      costo.replaceChildren(el("span", { class: "tenue" },
        `Hasta ${cuantas} llamadas a la API. No hay correcciones anteriores con qué estimar el costo.`));
    } else {
      costo.replaceChildren(el("strong", {}, `Costo estimado: ≈ ${textoConsumo(total)}`), " ",
        el("span", { class: "tenue" }, `(hasta ${cuantas} respuestas, con lo que costó en promedio cada una de las `
          + `últimas ${porRespuesta.llamadas.toLocaleString("es-CL")} correcciones con ${porRespuesta.modelo})`));
    }
    botonProbar.textContent = `Probar el criterio con ${cuantas || "?"} respuestas`;
  }
  for (const x of [todas, n]) x.addEventListener("input", actualizar);

  const seguir = (id) => seguirTrabajo(id, resultado, { extra: despues, alTerminar: () => historial.dibujar(semestre) });

  // Debajo de una prueba: la comparación si terminó, y volver a usar su prompt.
  function despues(t) {
    if (t.flujo !== "tests.experimento") return null;
    const usar = typeof t.argumentos?.prompt === "string" ? el("button", { class: "secundario", type: "button",
      onclick: () => {
        if (editado && !confirm("Vas a reemplazar el prompt que estás editando. ¿Seguir?")) return;
        cargar(t.argumentos.prompt);
        area.scrollIntoView({ behavior: "smooth", block: "center" });
      } }, "Usar el prompt de esta prueba") : null;
    const ruta = t.estado === "terminado" && !t.prueba
      ? (t.salida.match(/tests_semanales\/data\/experimento_[\w-]+\.csv/) || [])[0] : null;
    return el("div", {}, usar, ruta ? comparacion(semestre, ruta) : null);
  }

  async function pedir(prueba) {
    const argumentos = { prompt: area.value, n: Number(n.value), semilla: Number(semilla.value), prueba };
    if (!todas.checked) argumentos.semana = Number(semana.value);
    if (!argumentos.prompt.trim()) { resultado.replaceChildren(caja("aviso", "El prompt está vacío.")); return; }
    if (!(argumentos.n >= 1 && argumentos.n <= MAXIMO)) return;
    if (!prueba) {
      const total = estimarCosto({ n: argumentos.n, porRespuesta, largoCandidato: area.value.length,
        largoVigente: vigente.length, precios });
      const cuanto = total ? `Costo estimado: ≈ ${textoConsumo(total)}.` : `Hasta ${argumentos.n} llamadas a la API.`;
      if (!confirm(`Vas a reevaluar hasta ${argumentos.n} respuestas con este prompt. ${cuanto}\n\n`
        + "No se manda ningún correo ni cambia ninguna nota. ¿Seguir?")) return;
    }
    for (const b of [botonMuestra, botonProbar]) b.disabled = true;
    try {
      const id = await pedirTrabajo(semestre, "tests.experimento", argumentos);
      await seguir(id);
      historial.dibujar(semestre);
    } catch (e) {
      resultado.replaceChildren(caja("aviso", `No pude pedir el trabajo: ${e.message}`));
    } finally {
      for (const b of [botonMuestra, botonProbar]) b.disabled = false;
    }
  }
  botonMuestra.addEventListener("click", () => pedir(true));
  botonProbar.addEventListener("click", () => pedir(false));

  const historial = historialTrabajos({
    incluye: (t) => t.flujo === "tests.experimento",
    columna: ["Respuestas", (a) => `${a.n ?? "?"}${a.semana ? ` · sem. ${a.semana}` : ""}`],
    alElegir: (t) => { seguir(t.id); resultado.scrollIntoView({ behavior: "smooth", block: "start" }); },
  });

  // Lo que se carga aparte: el prompt vigente, el costo de antes y en qué
  // semanas se usó cada versión. Si algo falla, la vista sirve igual.
  leerTexto(semestre, VIGENTE).then(async (t) => {
    vigente = t;
    cargar(t);
    huellaVigente = await huella(t);
    pintarVersiones();
  }).catch(() => { area.disabled = false; area.value = ""; actualizar(); });
  Promise.all([api(`/api/consumo/${encodeURIComponent(semestre)}`), preciosApi()]).then(([consumos, p]) => {
    precios = p;
    porRespuesta = consumoPorRespuesta(consumos.map((c) => ({ ...c, usos: leerConsumo(c.lineas.join("\n")) })));
    actualizar();
  }).catch(() => {});
  if (versiones.length) {
    leerTexto(semestre, "log_envios.csv").then((texto) => {
      semanasDe = semanasPorVersion(objetosCsv(texto));
      pintarVersiones();
    }).catch(() => {});
  }
  historial.dibujar(semestre);
  actualizar();

  return [
    el("p", {}, "Reevalúa respuestas que ya se corrigieron con otro prompt y compara, respuesta por respuesta, "
      + "la nota y la originalidad de antes con las nuevas. No manda correos, no cambia notas ni el prompt del "
      + "semestre: para usar el prompt nuevo, cópialo en Prompts."),
    el("label", { class: "campo" }, "Partir de", origen),
    el("label", { class: "campo" }, "Prompt candidato", area),
    el("div", { class: "form-trabajo" },
      el("label", {}, "Cuántas respuestas", n),
      el("label", { class: "interruptor" }, todas, "Todas las semanas"),
      campoSemana,
      el("label", {}, "Semilla", semilla)),
    costo,
    el("div", { class: "acciones" }, botonMuestra, botonProbar),
    resultado,
    el("hr"),
    historial.nodo,
  ];
}
