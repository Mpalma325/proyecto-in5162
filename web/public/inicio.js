// Inicio: en qué va el curso, qué requiere atención y cuánto se ha gastado en
// la API. Los gráficos y las tablas del semestre están en Resultados.

import {
  api, caja, chipSemestre, el, fallidosSinResolver, fechaCorta, historialTrabajos, navegacion, preciosApi,
  seguirTrabajo,
} from "./comun.js";
import { flechasCiclo, leerCiclo } from "./ciclo.js";
import { formatoUsd, leerConsumo, sumarConsumo } from "./consumo.js";

document.getElementById("nav").replaceWith(navegacion());
const app = document.getElementById("app");

const enlaceTests = (texto, paso) => el("a", { href: `/tests#${paso}` }, texto);
const DIA = 864e5;

// ---------------------------------------------------------------- la semana

/** La semana abierta como tarjeta: su título y las flechas del ciclo. */
function tarjetaSemana(c) {
  const p = c.proximoPaso();
  if (!p?.paso) {
    return el("p", { class: "nota-pie" }, "Todas las semanas de preguntas.csv ya se enviaron y evaluaron.");
  }
  return el("section", { class: "franja-semana", "aria-label": "Semana en curso" },
    el("div", { class: "franja-cabeza" },
      el("div", {},
        el("div", { class: "franja-sobre" }, p.paso === "enviar" ? "Próxima semana" : "Semana en curso"),
        el("div", { class: "franja-titulo" }, `Semana ${p.semana}`))),
    flechasCiclo(c, enlaceTests));
}

// ---------------------------------------------------------------- requiere atención

/** Lo que alguien del equipo tiene que resolver, cada cosa con su enlace. */
function atencion(c, trabajos, consumo, precios) {
  const items = [];
  const sinNota = c.sinNota();
  if (sinNota) {
    items.push(el("li", {}, `${sinNota} ${sinNota === 1 ? "respuesta" : "respuestas"} sin nota. `,
      el("a", { href: "/resultados#Pendientes" }, "Ver")));
  }
  for (const f of fallidosSinResolver(trabajos)) {
    const sobre = f.argumentos?.semana ? ` de la semana ${f.argumentos.semana}` : f.argumentos?.tarea ? ` de ${f.argumentos.tarea}` : "";
    items.push(el("li", {}, `Falló ${nombreTrabajo(f)}${sobre} (${fechaCorta(new Date(f.creado))}) y no se volvió a correr. `,
      el("a", { href: "#resultado", onclick: (e) => { e.preventDefault(); verTrabajo(f); } }, "Ver")));
  }
  const sinPrecio = sumarConsumo(consumo.flatMap((t) => leerConsumo(t.lineas.join("\n"))), precios).sinPrecio;
  if (sinPrecio.length) {
    items.push(el("li", {}, `Faltan los precios de la API de ${sinPrecio.join(", ")}. `,
      el("a", { href: "/datos#parametros" }, "Cargarlos")));
  }
  return items.length ? el("section", { class: "atencion-inicio" }, el("h2", {}, "Requiere atención"),
    el("ul", {}, items)) : null;
}

const NOMBRES = {
  "tests.enviar": "el envío", "tests.evaluar": "la evaluación", "tests.resumen": "el resumen",
  "tests.tutoria": "la respuesta a dudas", "tests.experimento": "la prueba de criterio",
  "tareas.generar": "la generación de preguntas", "tareas.enviar": "el envío", "tareas.recolectar": "la recolección",
  "tareas.corregir": "la corrección", "tareas.segunda": "la segunda oportunidad", "datos.ajustar": "el ajuste de nota",
};
const nombreTrabajo = (t) => NOMBRES[t.flujo] || t.flujo;

// ---------------------------------------------------------------- gasto en la API

const GRUPOS_FLUJO = [
  ["Evaluaciones", (f) => f === "tests.evaluar"],
  ["Dudas de alumnos", (f) => f === "tests.tutoria"],
  ["Resúmenes", (f) => f === "tests.resumen"],
  ["Pruebas de criterio", (f) => f === "tests.experimento"],
  ["Tareas", (f) => f.startsWith("tareas.")],
];

/** Cuánto se gastó: los últimos 7 y 30 días, el semestre, y en qué. */
function gasto(consumo, precios) {
  const total = (lista) => sumarConsumo(lista.flatMap((t) => leerConsumo(t.lineas.join("\n"))), precios);
  const desde = (dias) => consumo.filter((t) => Date.now() - new Date(t.creado) <= dias * DIA);
  const monto = (t) => (t.llamadas ? (t.sinPrecio.length && !t.usd
    ? `${(t.entrada + t.salida).toLocaleString("es-CL")} tokens` : formatoUsd(t.usd)) : "—");
  const tarjeta = (etiqueta, t) => el("div", { class: "kpi" }, el("div", { class: "etiqueta" }, etiqueta),
    el("div", { class: "valor" }, monto(t)),
    el("div", { class: "sub" }, t.llamadas ? `${t.llamadas.toLocaleString("es-CL")} llamadas` : "sin llamadas"));
  if (!consumo.length) {
    return el("section", {}, el("h2", {}, "Gasto en la API"),
      el("p", { class: "nota-pie" }, "Todavía no hay trabajos con consumo registrado."));
  }
  const semestre = total(consumo);
  const primero = consumo.map((t) => new Date(t.creado)).sort((a, b) => a - b)[0];
  const porGrupo = GRUPOS_FLUJO.map(([nombre, es]) => [nombre, total(consumo.filter((t) => es(t.flujo)))])
    .filter(([, t]) => t.llamadas);
  return el("section", {}, el("h2", {}, "Gasto en la API"),
    el("div", { class: "kpis k3" }, tarjeta("Últimos 7 días", total(desde(7))), tarjeta("Últimos 30 días", total(desde(30))),
      tarjeta("Semestre", semestre)),
    el("p", { class: "nota-pie" }, [
      porGrupo.map(([nombre, t]) => `${nombre}: ${monto(t)}`).join(" · "),
      `Registrado desde el ${fechaCorta(primero)}.`,
    ].filter(Boolean).join(". ")));
}

// ---------------------------------------------------------------- pantalla

const detalleTrabajo = el("div", { id: "resultado" });
function verTrabajo(t) {
  seguirTrabajo(t.id, detalleTrabajo);
  detalleTrabajo.scrollIntoView({ behavior: "smooth", block: "start" });
}
const historial = historialTrabajos({
  incluye: () => true,
  columna: ["Semana o tarea", (a) => a.semana ?? a.tarea ?? ""],
  alElegir: verTrabajo,
});

async function iniciar() {
  try {
    const semestres = await api("/api/semestres");
    const activo = semestres.find((s) => s.activo);
    if (!activo) {
      app.replaceChildren(caja("aviso", el("span", {}, "No hay un semestre activo. ",
        el("a", { href: "/datos" }, "Elígelo o créalo en Configuración"), ".")));
      return;
    }
    const semestre = activo.id;
    const [c, trabajos, consumo, precios] = await Promise.all([
      leerCiclo(semestre).catch(() => null),
      api(`/api/trabajos?semestre=${encodeURIComponent(semestre)}`).catch(() => []),
      api(`/api/consumo/${encodeURIComponent(semestre)}`).catch(() => []),
      preciosApi(),
    ]);
    app.replaceChildren(...[
      el("div", { class: "cabeza-operacion" }, chipSemestre(semestre)),
      c ? tarjetaSemana(c)
        : caja("aviso", "No pude leer en qué va el curso (notas.csv)."),
      c ? atencion(c, trabajos, consumo, precios) : null,
      gasto(consumo, precios),
      historial.nodo,
      detalleTrabajo,
    ].filter(Boolean));
    historial.dibujar(semestre);
  } catch (e) {
    app.replaceChildren(caja("aviso", `No pude cargar la página: ${e.message}`));
  }
}

iniciar();
