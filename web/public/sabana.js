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
// Por defecto van todas salvo las técnicas.
const APAGADAS = new Set(["EvaluacionHTML", "MessageIdEnvio"]);
// Filtros de filas: columna -> etiqueta.
const FILTROS = [["Flujo", "Flujo"], ["Item", "Semana o tarea"], ["Variante", "Variante"], ["Estado", "Estado"]];

const urlSabana = (semestre) => `/api/archivo/${encodeURIComponent(semestre)}/${RUTA}`;
const ordenItem = (a, b) => (Number(a) - Number(b)) || a.localeCompare(b, "es", { numeric: true });

/** La sección completa: preparar la sábana, elegir columnas y filas, descargar. */
export function seccionSabana(semestre) {
  const cuerpo = el("div");
  const estado = el("div");
  const preparar = el("button", { class: "primario", type: "button" }, "Preparar la sábana actualizada");
  preparar.addEventListener("click", async () => {
    preparar.disabled = true;
    estado.replaceChildren(caja("info", "Armando la sábana en el motor… (solo lee, tarda unos segundos)"));
    try {
      const id = await pedirTrabajo(semestre, "datos.sabana", {});
      const salida = el("div", { hidden: true });
      estado.append(salida);
      await seguirTrabajo(id, salida, {
        alTerminar: async (t) => {
          preparar.disabled = false;
          if (t.estado !== "terminado") { salida.hidden = false; return; }
          estado.replaceChildren();
          await cargar();
        },
      });
    } catch (e) {
      preparar.disabled = false;
      estado.replaceChildren(caja("aviso", `No pude pedirla: ${e.message}`));
    }
  });

  async function cargar() {
    const r = await fetch(urlSabana(semestre), { cache: "no-store" });
    if (!r.ok) {
      cuerpo.replaceChildren(el("p", { class: "nota-pie" }, "Todavía no hay una sábana de este semestre: prepárala."));
      return;
    }
    const { columnas, filas } = leerCsv(await r.text());
    const lista = await api(`/api/archivos/${encodeURIComponent(semestre)}?prefijo=exportes/`).catch(() => []);
    const info = lista.find((a) => a.ruta === RUTA);
    cuerpo.replaceChildren(...selector(semestre, columnas, filas, info?.subido));
  }

  cargar().catch((e) => cuerpo.replaceChildren(caja("aviso", `No pude leer la sábana: ${e.message}`)));
  return el("section", { class: "sabana" },
    el("h4", {}, "Sábana de datos"),
    el("p", { class: "nota-pie" }, "Una fila por alumno y semana (o tarea), con la pregunta exacta que recibió según "
      + "su variante, la pauta, su respuesta, la evaluación del modelo, los ajustes manuales y las tutorías. Elige "
      + "columnas y filas y descárgala en CSV."),
    el("div", { class: "acciones" }, preparar), estado, cuerpo);
}

function selector(semestre, columnas, filas, subido) {
  const conocidas = new Set(GRUPOS.flatMap(([, cs]) => cs));
  const grupos = [...GRUPOS.map(([g, cs]) => [g, cs.filter((c) => columnas.includes(c))]),
    ["Otras", columnas.filter((c) => !conocidas.has(c))]].filter(([, cs]) => cs.length);
  const idx = Object.fromEntries(columnas.map((c, i) => [c, i]));

  const marcas = new Map(columnas.map((c) => [c, el("input", { type: "checkbox", checked: !APAGADAS.has(c), value: c })]));
  const filtros = new Map();
  const busqueda = el("input", { type: "text", placeholder: "nombre o correo", size: 20 });
  const cuenta = el("p", { class: "nota-pie" });
  const descargarBtn = el("button", { class: "primario", type: "button" }, "Descargar CSV");

  const elegidas = () => columnas.filter((c) => marcas.get(c).checked);
  const visibles = () => {
    const q = busqueda.value.trim().toLowerCase();
    return filas.filter((f) => [...filtros].every(([col, set]) => set.size === 0 || set.has(f[idx[col]]))
      && (!q || `${f[idx.Nombre] ?? ""} ${f[idx.Correo] ?? ""}`.toLowerCase().includes(q)));
  };
  const actualizar = () => {
    const n = visibles().length;
    cuenta.textContent = `${n} de ${filas.length} filas · ${elegidas().length} de ${columnas.length} columnas`;
    descargarBtn.disabled = !n || !elegidas().length;
  };

  const bloquesFiltro = FILTROS.filter(([col]) => col in idx).map(([col, etiqueta]) => {
    const valores = [...new Set(filas.map((f) => f[idx[col]]).filter(Boolean))].sort(ordenItem);
    const set = new Set();
    filtros.set(col, set);
    return el("div", { class: "filtro" }, el("span", {}, etiqueta),
      el("div", { class: "chips" }, valores.map((v) => {
        const chip = el("button", { class: "chip", type: "button", "aria-pressed": "false" }, v);
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
    const todas = (v) => { cs.forEach((c) => { marcas.get(c).checked = v; }); actualizar(); };
    return el("fieldset", { class: "seccion" }, el("legend", {}, g),
      el("div", { class: "acciones" },
        el("button", { class: "enlace", type: "button", onclick: () => todas(true) }, "Todas"),
        el("button", { class: "enlace", type: "button", onclick: () => todas(false) }, "Ninguna")),
      el("div", { class: "lista-casillas" }, cs.map((c) => {
        marcas.get(c).addEventListener("change", actualizar);
        return el("label", {}, marcas.get(c), c);
      })));
  });

  descargarBtn.addEventListener("click", () => {
    const cols = elegidas();
    const texto = exportarCsv(cols, visibles().map((f) => cols.map((c) => f[idx[c]])));
    descargar(`sabana_${semestre}.csv`, texto);
  });

  actualizar();
  const cuando = subido ? new Date(subido).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" }) : "";
  return [
    el("p", { class: "nota-pie" }, `Sábana preparada ${cuando ? `el ${cuando}` : ""}: ${filas.length} filas. `
      + "Si hubo evaluaciones después, prepárala de nuevo."),
    el("h4", {}, "Filas"),
    el("div", { class: "filtros-sabana" }, ...bloquesFiltro,
      el("div", { class: "filtro" }, el("span", {}, "Alumno"), busqueda)),
    el("p", { class: "nota-pie" }, "Sin marcar nada en un filtro, entran todas. Marcando, solo esas."),
    el("h4", {}, "Columnas"),
    ...bloquesColumnas,
    cuenta,
    el("div", { class: "acciones" }, descargarBtn),
  ];
}
