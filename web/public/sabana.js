// La sábana de datos: una fila por alumno e ítem, con la pregunta que recibió,
// su variante, la pauta, la respuesta, la evaluación, los ajustes y más.
// La arma el motor (modulos/sabana.py, trabajo "datos.sabana") y queda en
// exportes/sabana.csv; acá se eligen columnas y filas y se descarga.

import { api, caja, el, pedirTrabajo, seguirTrabajo } from "./comun.js";
import { descargar, exportarCsv, leerCsv } from "./csv.js";

const RUTA = "exportes/sabana.csv";

// Las columnas de modulos/sabana.py, agrupadas para elegirlas. Las que no
// estén acá (si el script agrega otras) van al grupo "Otras".
const GRUPOS = [
  ["Alumno", ["Semestre", "Flujo", "Item", "Nombre", "Correo", "EnRoster", "Variante", "GrupoTarea", "ParteTarea"]],
  ["Pregunta", ["Tema", "FechaEntrega", "NumPreguntas", "Pregunta", "Pauta", "SegundaOportunidad"]],
  ["Envío y respuesta", ["Estado", "Enviado", "FechaEnvio", "MessageIdEnvio", "Respondio", "FechaRespuesta",
    "Respuesta", "LargoRespuesta"]],
  ["Evaluación", ["FechaEvaluacion", "Nota", "NotaTexto", "NotaDelModelo", "Originalidad", "Modelo",
    "TokensEntrada", "TokensSalida", "EvaluacionTexto", "EvaluacionHTML", "AjusteManual", "MotivoAjuste"]],
  ["Tutoría", ["Repreguntas", "Tutorias"]],
];
// Las técnicas: sirven para depurar el sistema, no para leer ni analizar respuestas.
const TECNICAS = new Set(["MessageIdEnvio", "EvaluacionHTML", "TokensEntrada", "TokensSalida"]);
const RESPUESTAS_Y_NOTAS = ["Item", "Tema", "Nombre", "Correo", "Variante", "Estado", "Pregunta", "Respuesta",
  "Nota", "Originalidad", "EvaluacionTexto"];
// Tres formas de elegir columnas de una vez. Son listas explícitas: el detalle
// casilla por casilla queda plegado para quien lo necesite.
const PREAJUSTES = [
  { id: "respuestas", nombre: "Respuestas y notas", elegir: (cols) => cols.filter((c) => RESPUESTAS_Y_NOTAS.includes(c)),
    explica: () => "Semana, alumno, pregunta, respuesta, nota, originalidad y evaluación." },
  { id: "analisis", nombre: "Para análisis", elegir: (cols) => cols.filter((c) => !TECNICAS.has(c)),
    explica: () => "Todo menos el identificador del correo, la evaluación en HTML y los tokens." },
  { id: "todo", nombre: "Todo", elegir: (cols) => cols,
    explica: (cols) => `Las ${cols.length} columnas.` },
];
const PREAJUSTE_INICIAL = "analisis";
// Filtros de filas: columna -> etiqueta.
const FILTROS = [["Flujo", "Flujo"], ["Item", "Semana o tarea"], ["Variante", "Variante"], ["Estado", "Estado"]];

const urlSabana = (semestre) => `/api/archivo/${encodeURIComponent(semestre)}/${RUTA}`;
const ordenItem = (a, b) => (Number(a) - Number(b)) || a.localeCompare(b, "es", { numeric: true });

// Lo que lee modulos/sabana.py. Si alguno se escribió después de la sábana, la
// sábana está atrasada: le falta una evaluación, una tutoría o un ajuste.
const esFuente = (ruta) => ["alumnos.csv", "notas.csv", "log_envios.csv", "tests_semanales/data/preguntas.csv"]
  .includes(ruta) || /^tareas\/data\/salidas\/[^/]+\.csv$/.test(ruta);

/** { sabana: su entrada en la lista de archivos o null, atrasada }. */
export function estadoSabana(archivos) {
  const sabana = archivos.find((a) => a.ruta === RUTA) ?? null;
  const ultimoCambio = archivos.filter((a) => esFuente(a.ruta)).map((a) => a.subido).sort().pop();
  return { sabana, atrasada: !sabana || Boolean(ultimoCambio && ultimoCambio > sabana.subido) };
}

const fecha = (iso) => (iso ? new Date(iso).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" }) : "");

/**
 * La sección completa: la sábana, elegir columnas y filas, descargar.
 * Al abrirla se muestra la versión que haya y se revisa si hubo cambios desde
 * que se armó; si los hubo, se vuelve a armar en segundo plano en el motor
 * (solo lee, unos segundos) y la vista se refresca al terminar, sin perder lo
 * elegido. Si ya hay un trabajo de sábana pedido, se sigue ese.
 */
export function seccionSabana(semestre) {
  const cuerpo = el("div");
  const aviso = el("div");
  const rearmar = el("button", { class: "secundario", type: "button", hidden: true }, "Volver a armarla");
  rearmar.addEventListener("click", () => armar(false));
  let armando = false;
  let vista = null; // el selector dibujado: para conservar lo elegido al refrescar

  const listar = () => api(`/api/archivos/${encodeURIComponent(semestre)}`);

  /** Un trabajo de sábana ya pedido o corriendo (de otra persona, o de esta misma página). */
  async function trabajoEnCurso() {
    try {
      const lista = await api(`/api/trabajos?semestre=${encodeURIComponent(semestre)}`);
      return lista.find((t) => t.flujo === "datos.sabana" && (t.estado === "pendiente" || t.estado === "corriendo")) ?? null;
    } catch {
      return null;
    }
  }

  async function armar(automatico) {
    if (armando) return;
    armando = true;
    rearmar.hidden = true;
    const habia = Boolean(vista);
    const mensaje = caja("info", !habia ? "Armando la sábana…"
      : "Actualizando con los últimos cambios. La versión de abajo se puede descargar mientras tanto.");
    aviso.replaceChildren(mensaje);
    if (vista) vista.marcarActualizando(true);
    try {
      const previo = await trabajoEnCurso();
      if (previo) mensaje.append(` (pedida por ${previo.pedido_por || "otra persona"})`);
      const id = previo ? previo.id : await pedirTrabajo(semestre, "datos.sabana", {});
      const salida = el("div", { hidden: true });
      aviso.append(salida);
      await seguirTrabajo(id, salida, {
        alTerminar: async (t) => {
          armando = false;
          if (t.estado === "terminado") {
            aviso.replaceChildren();
          } else {
            // Si otra persona la armó al mismo tiempo, la nube igual quedó al día.
            const { atrasada } = estadoSabana(await listar().catch(() => []));
            aviso.replaceChildren(atrasada ? caja("aviso", habia
              ? "No pude actualizar la sábana; abajo está la versión anterior." : "No pude armar la sábana.") : "");
            if (atrasada) { aviso.append(salida); salida.hidden = false; }
          }
          await cargar();
        },
      });
    } catch (e) {
      armando = false;
      aviso.replaceChildren(caja("aviso", `No pude actualizar la sábana: ${e.message}.`
        + (habia ? " Abajo está la versión anterior." : "")));
      await cargar();
    }
  }

  async function cargar({ actualizando = armando } = {}) {
    const archivos = await listar().catch(() => null);
    const { sabana, atrasada } = estadoSabana(archivos || []);
    // Con la lista a mano no se pide un archivo que no existe.
    const r = archivos && !sabana ? null : await fetch(urlSabana(semestre), { cache: "no-store" });
    if (!r || !r.ok) {
      cuerpo.replaceChildren(actualizando ? "" : el("p", { class: "nota-pie" }, "Todavía no hay una sábana de este semestre."));
      rearmar.textContent = "Armarla ahora";
      rearmar.hidden = armando;
      return;
    }
    const { columnas, filas } = leerCsv(await r.text());
    const previo = vista ? vista.leer() : null;
    vista = selector(semestre, columnas, filas, { subido: sabana?.subido, alDia: !atrasada, actualizando, previo });
    cuerpo.replaceChildren(...vista.nodos);
    rearmar.textContent = "Volver a armarla";
    rearmar.hidden = armando;
  }

  (async () => {
    let archivos = null;
    try { archivos = await listar(); } catch { /* sin la lista, se muestra la que haya */ }
    if (!archivos) { await cargar(); return; }
    if (!archivos.some((a) => esFuente(a.ruta))) {
      cuerpo.replaceChildren(el("p", { class: "nota-pie" }, "Este semestre todavía no tiene datos para armar la sábana."));
      return;
    }
    const { sabana, atrasada } = estadoSabana(archivos);
    // Primero la versión que hay, para poder usarla mientras se actualiza.
    if (sabana) await cargar({ actualizando: atrasada });
    if (atrasada) await armar(true);
  })().catch((e) => cuerpo.replaceChildren(caja("aviso", `No pude leer la sábana: ${e.message}`)));

  return el("section", { class: "sabana" },
    el("h3", {}, "Sábana completa"),
    el("p", { class: "nota-pie" }, "Una fila por alumno y semana o tarea: pregunta, pauta, respuesta, evaluación, "
      + "ajustes y tutorías. Tiene sus propios filtros."),
    aviso, cuerpo, el("div", { class: "acciones" }, rearmar));
}

/**
 * Elegir filas y columnas y descargar. `previo` es lo que se había elegido en
 * la versión anterior de la sábana: se conserva al refrescarla.
 */
function selector(semestre, columnas, filas, { subido, alDia, actualizando, previo }) {
  const conocidas = new Set(GRUPOS.flatMap(([, cs]) => cs));
  const grupos = [...GRUPOS.map(([g, cs]) => [g, cs.filter((c) => columnas.includes(c))]),
    ["Otras", columnas.filter((c) => !conocidas.has(c))]].filter(([, cs]) => cs.length);
  const idx = Object.fromEntries(columnas.map((c, i) => [c, i]));

  const marcas = new Map(columnas.map((c) => [c, el("input", { type: "checkbox", value: c })]));
  const filtros = new Map();
  const busqueda = el("input", { type: "text", placeholder: "nombre o correo", size: 20, "aria-label": "Alumno" });
  busqueda.value = previo ? previo.q : "";
  const cuenta = el("p", { class: "nota-pie" });
  const version = el("p", { class: "nota-pie version-sabana" });
  const explicacion = el("p", { class: "nota-pie" });
  const resumenColumnas = el("summary");
  const descargarBtn = el("button", { class: "primario", type: "button" }, "Descargar la sábana (CSV)");

  let preajuste = previo ? previo.preajuste : PREAJUSTE_INICIAL;
  const aplicar = (id) => {
    const sel = new Set(PREAJUSTES.find((p) => p.id === id).elegir(columnas));
    marcas.forEach((m, c) => { m.checked = sel.has(c); });
  };
  if (preajuste) aplicar(preajuste);
  else marcas.forEach((m, c) => { m.checked = previo.columnas.has(c); });

  const elegidas = () => columnas.filter((c) => marcas.get(c).checked);
  // Si lo marcado a mano coincide con un preajuste, se muestra ese como elegido.
  const reconocer = () => {
    const sel = elegidas().join("|");
    preajuste = PREAJUSTES.find((p) => p.elegir(columnas).join("|") === sel)?.id ?? null;
  };
  const visibles = () => {
    const q = busqueda.value.trim().toLowerCase();
    return filas.filter((f) => [...filtros].every(([col, set]) => set.size === 0 || set.has(f[idx[col]]))
      && (!q || `${f[idx.Nombre] ?? ""} ${f[idx.Correo] ?? ""}`.toLowerCase().includes(q)));
  };

  const chipsPreajuste = PREAJUSTES.map((p) => {
    const chip = el("button", { class: "chip", type: "button", "aria-pressed": "false" }, p.nombre);
    chip.addEventListener("click", () => { preajuste = p.id; aplicar(p.id); actualizar(); });
    return [p.id, chip];
  });

  const actualizar = () => {
    const n = visibles().length;
    const m = elegidas().length;
    cuenta.textContent = `${n} de ${filas.length} filas · ${m} de ${columnas.length} columnas`;
    descargarBtn.disabled = !n || !m;
    chipsPreajuste.forEach(([id, chip]) => chip.setAttribute("aria-pressed", String(id === preajuste)));
    const p = PREAJUSTES.find((x) => x.id === preajuste);
    explicacion.textContent = p ? p.explica(columnas) : "Columnas elegidas a mano.";
    resumenColumnas.textContent = `Elegir columnas a mano (${m} de ${columnas.length})`;
  };

  const marcarActualizando = (si) => {
    version.textContent = `${alDia && !si ? "Al día" : "Versión anterior"}${subido ? ` (armada el ${fecha(subido)})` : ""}: `
      + `${filas.length} filas${si ? " · se está actualizando" : ""}.`;
  };
  marcarActualizando(actualizando);

  const bloquesFiltro = FILTROS.filter(([col]) => col in idx).map(([col, etiqueta]) => {
    const valores = [...new Set(filas.map((f) => f[idx[col]]).filter(Boolean))].sort(ordenItem);
    const antes = previo?.filtros.get(col);
    const set = new Set(antes ? valores.filter((v) => antes.has(v)) : []);
    filtros.set(col, set);
    return el("div", { class: "filtro" }, el("span", {}, etiqueta),
      el("div", { class: "chips" }, valores.map((v) => {
        const chip = el("button", { class: "chip", type: "button", "aria-pressed": String(set.has(v)) }, v);
        chip.addEventListener("click", () => {
          if (set.has(v)) set.delete(v); else set.add(v);
          chip.setAttribute("aria-pressed", String(set.has(v)));
          actualizar();
        });
        return chip;
      })));
  });
  busqueda.addEventListener("input", actualizar);

  const bloquesColumnas = grupos.map(([g, cs]) => {
    const todas = (v) => { cs.forEach((c) => { marcas.get(c).checked = v; }); reconocer(); actualizar(); };
    return el("fieldset", { class: "seccion" }, el("legend", {}, g),
      el("div", { class: "acciones" },
        el("button", { class: "enlace", type: "button", onclick: () => todas(true) }, "Todas"),
        el("button", { class: "enlace", type: "button", onclick: () => todas(false) }, "Ninguna")),
      el("div", { class: "lista-casillas" }, cs.map((c) => {
        marcas.get(c).addEventListener("change", () => { reconocer(); actualizar(); });
        return el("label", {}, marcas.get(c), c);
      })));
  });

  descargarBtn.addEventListener("click", () => {
    const cols = elegidas();
    const texto = exportarCsv(cols, visibles().map((f) => cols.map((c) => f[idx[c]])));
    descargar(`sabana_${semestre}.csv`, texto);
  });

  actualizar();
  return {
    nodos: [
      version,
      el("h4", {}, "Filas"),
      el("div", { class: "filtros-sabana" }, ...bloquesFiltro,
        el("div", { class: "filtro" }, el("span", {}, "Alumno"), busqueda)),
      el("h4", {}, "Columnas"),
      el("div", { class: "chips preajustes" }, chipsPreajuste.map(([, chip]) => chip)),
      explicacion,
      el("details", { class: "columnas-a-mano" }, resumenColumnas, el("div", { class: "contenido" }, bloquesColumnas)),
      cuenta,
      el("div", { class: "acciones" }, descargarBtn),
    ],
    leer: () => ({
      preajuste, columnas: new Set(elegidas()), q: busqueda.value,
      filtros: new Map([...filtros].map(([col, set]) => [col, new Set(set)])),
    }),
    marcarActualizando,
  };
}
