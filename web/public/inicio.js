// Inicio: en qué va el curso, qué requiere atención y cuánto se ha gastado en
// la API. Los gráficos y las tablas del semestre están en Resultados.

import {
  api, caja, chipSemestre, el, fallidosSinResolver, fechaCorta, historialTrabajos, navegacion, nombreFlujo, normalizar,
  preciosApi, seguirTrabajo, sobreQue,
} from "./comun.js";
import { flechasCiclo, leerCiclo } from "./ciclo.js";
import { leerCsv } from "./csv.js";
import { formatoUsd, leerConsumo, notaMezcla, sumarConsumo } from "./consumo.js";

document.getElementById("nav").replaceWith(navegacion());
const app = document.getElementById("app");

const enlaceTests = (texto, paso) => el("a", { href: `/tests#${paso}` }, texto);
const DIA = 864e5;

// ---------------------------------------------------------------- la semana

/** La semana abierta como tarjeta: su título y las flechas del ciclo. */
function tarjetaSemana(c) {
  const p = c.proximoPaso();
  // Formato nuevo (preguntas.csv con Instancia): sin semanas, cada una con su envío y su cierre.
  const legado = c.legado !== false;
  if (!p?.paso) {
    return el("p", { class: "nota-pie" }, legado ? "Todas las semanas de preguntas.csv ya se enviaron y evaluaron."
      : "Todas las instancias de preguntas.csv ya se enviaron y evaluaron.");
  }
  const sobre = legado ? (p.paso === "enviar" ? "Próxima semana" : "Semana en curso")
    : p.paso === "enviar" ? "Próxima instancia"
      : p.abiertas > 1 ? `Abierta, y ${p.abiertas - 1} más` : "Abierta";
  return el("section", { class: "franja-semana", "aria-label": legado ? "Semana en curso" : "Instancia en curso" },
    el("div", { class: "franja-cabeza" },
      el("div", {},
        el("div", { class: "franja-sobre" }, sobre),
        el("div", { class: "franja-titulo" }, legado ? `Semana ${p.semana}` : c.nombre(p.semana)))),
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
  // Las correcciones que esperan al docente: no salen solas (ni en automático
  // si el semestre pasó a revisión). Las descartadas ya están cerradas.
  for (const [n, cuantas] of c.porRevisar ? c.porRevisar() : []) {
    items.push(el("li", {}, avisoPorRevisar(cuantas, c.nombre(n)), " ",
      el("a", { href: `/tests#revisar/${n}` }, "Revisar")));
  }
  for (const f of fallidosSinResolver(trabajos)) {
    const sobre = f.argumentos?.instancia ? ` de ${sobreQue(f.argumentos)}`
      : f.argumentos?.semana ? ` de la semana ${f.argumentos.semana}` : f.argumentos?.tarea ? ` de ${f.argumentos.tarea}` : "";
    const veces = f.intentos > 1 ? `, ${f.intentos} intentos` : "";
    items.push(el("li", {}, `Falló ${nombreTrabajo(f)}${sobre} (${fechaCorta(new Date(f.creado))}${veces}) y no se volvió a correr. `,
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

/** «12 correcciones esperando revisión (Control 2)». */
export function avisoPorRevisar(cuantas, nombre) {
  return `${cuantas} ${cuantas === 1 ? "corrección esperando" : "correcciones esperando"} revisión (${nombre}).`;
}

const NOMBRES = {
  "tests.enviar": "el envío", "tests.evaluar": "la evaluación", "tests.feedback": "el envío del feedback",
  "tests.resumen": "el resumen",
  "tests.tutoria": "la respuesta a dudas", "tests.experimento": "la prueba de criterio",
  "tareas.generar": "la generación de preguntas", "tareas.enviar": "el envío", "tareas.recolectar": "la recolección",
  "tareas.corregir": "la corrección", "tareas.segunda": "la segunda oportunidad", "datos.ajustar": "el ajuste de nota",
  "datos.sabana": "el armado de la sábana", "datos.panel": "la actualización de los resultados",
  "tareas.chequeo": "la revisión de entregas", "tests.chequeo": "el chequeo",
};
const nombreTrabajo = (t) => NOMBRES[t.flujo] || `«${nombreFlujo(t)}»`;

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
    el("div", { class: "valor", title: notaMezcla(t) || null }, monto(t)),
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
    el("p", { class: "nota-pie" }, `${[
      porGrupo.map(([nombre, t]) => `${nombre}: ${monto(t)}`).join(" · "),
      `Registrado desde el ${fechaCorta(primero)}`,
      // Los trabajos de antes, o los de un modelo que no tenía precio cuando
      // corrieron, no traen su US$: se calculan con los precios de hoy.
      notaMezcla(semestre) ? "Los trabajos que no registraron su costo se calcularon con los precios de hoy" : "",
    ].filter(Boolean).join(". ")}.`));
}

// ---------------------------------------------------------------- pantalla

// Lo que sigue después de un trabajo se hace en su página: desde aquí, un enlace.
const SIGUE_EN = {
  "tests.evaluar": ["/tests#evaluar", "Elegir cuáles evaluar en Tests › Evaluar respuestas"],
  "tareas.corregir": ["/tareas#corregir", "Elegir cuáles corregir en Tareas › Corregir"],
};
function siguePaso(t) {
  if (t.flujo === "tests.experimento" && t.estado === "terminado") {
    return el("p", {}, el("a", { href: "/datos#datos/probar" },
      "Ver la comparación y descargar el CSV en Configuración › La IA › Probar criterio"));
  }
  const sigue = SIGUE_EN[t.flujo];
  if (!sigue || !t.prueba || t.estado !== "terminado") return null;
  return el("p", {}, el("a", { href: sigue[0] }, sigue[1]));
}

const detalleTrabajo = el("div", { id: "resultado" });
function verTrabajo(t) {
  seguirTrabajo(t.id, detalleTrabajo, { extra: siguePaso });
  detalleTrabajo.scrollIntoView({ behavior: "smooth", block: "start" });
}
const historial = historialTrabajos({
  incluye: () => true,
  columna: ["Semana o tarea", (a) => (a.instancia ? sobreQue(a) : a.semana ?? a.tarea ?? "")],
  alElegir: verTrabajo,
});

/** Un campo chico para ir directo a la ficha de un alumno (Resultados › Alumnos). */
function buscadorAlumno(semestre) {
  const lista = el("datalist", { id: "lista-alumnos" });
  const campo = el("input", {
    type: "search", list: "lista-alumnos", placeholder: "Buscar alumno…", "aria-label": "Buscar alumno",
  });
  let alumnos = [];
  fetch(`/api/archivo/${encodeURIComponent(semestre)}/alumnos.csv`, { cache: "no-store" })
    .then((r) => (r.ok ? r.text() : ""))
    .then((texto) => {
      if (!texto) return;
      const d = leerCsv(texto);
      const [iN, iC] = [d.columnas.indexOf("Nombre"), d.columnas.indexOf("Correo")];
      alumnos = d.filas.map((f) => ({ nombre: (f[iN] || "").trim(), correo: (f[iC] || "").trim().toLowerCase() }))
        .filter((a) => a.correo);
      lista.replaceChildren(...alumnos.map((a) => el("option", { value: `${a.nombre} · ${a.correo}` })));
    })
    .catch(() => {});
  // Sin tildes ni mayúsculas: "perez" encuentra a Pérez.
  const ir = () => {
    const q = normalizar(campo.value.trim());
    if (!q) return;
    const a = alumnos.find((x) => q.endsWith(x.correo) || x.correo.includes(q))
      || alumnos.find((x) => normalizar(x.nombre).includes(q));
    if (a) {
      location.href = `/resultados#Alumnos/${encodeURIComponent(a.correo)}`;
      return;
    }
    campo.setCustomValidity("No encontré a ese alumno.");
    campo.reportValidity();
  };
  campo.addEventListener("input", () => campo.setCustomValidity(""));
  campo.addEventListener("change", ir);
  return el("form", { class: "buscar-alumno", role: "search", onsubmit: (e) => { e.preventDefault(); ir(); } },
    campo, lista);
}

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
      el("div", { class: "cabeza-operacion cabeza-inicio" }, chipSemestre(semestre), buscadorAlumno(semestre)),
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
