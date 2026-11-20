// Tareas: la misma página de Streamlit, operando en la nube.
//
// Los cuatro pasos (generar, enviar, recolectar, corregir) son trabajos del
// motor, igual que en Tests Semanales. El chequeo de las entregas también: lee
// los HTML en el motor y deja el resultado en tareas/cache/, que esta página
// dibuja. No llama al modelo.
//
// Lo que antes había que hacer a mano en los archivos se hace aquí: elegir el
// correo de quien no calzó con la lista de alumnos (paso 1), corregir una
// pregunta antes de enviarla y programar el envío con su plazo (paso 2), y leer
// y editar las correcciones antes de mandarlas (paso 4).

import {
  api, barraPestanas, caja, chipSemestre, confirmar, el, elegirCandidatos, fechaCorta, historialTrabajos, horaCorta,
  navegacion, pedirTrabajo, respuestaLegible, seguirTrabajo, tareasConocidas, textoProgramado, conDetalle,
} from "./comun.js";
import { escribirCsv, leerCsv } from "./csv.js";

document.getElementById("nav").replaceWith(navegacion());
const app = document.getElementById("app");

let semestre = null;
let archivos = [];
let tarea = null;
let tareaPorDefecto = "T1";

// `id` va en la URL y `flujo` es el trabajo que se pide: no cambian. Los
// botones nombran la tarea elegida (`tarea`), que es solo texto: el dato que
// se manda sigue saliendo de la variable, no del botón.
const PESTANAS = [
  { id: "generar", titulo: "1 · Generar preguntas", flujo: "tareas.generar" },
  {
    id: "enviar", titulo: "2 · Enviar preguntas", flujo: "tareas.enviar",
    vista: (p, d) => vistaEnviar(p, d),
  },
  {
    id: "recolectar", titulo: "3 · Recolectar respuestas", flujo: "tareas.recolectar",
    info: "Solo lee el buzón. Se puede repetir.",
    boton: () => `Recolectar respuestas de ${tarea}`,
  },
  {
    id: "corregir", titulo: "4 · Corregir", flujo: "tareas.corregir",
    prueba: "Solo simular",
    // Por defecto, las correcciones esperan revisión: se leen y se editan abajo
    // antes de mandarlas (vistaRevision).
    noEnviar: "Revisarlas antes de mandar el feedback", noEnviarMarcado: true,
    botonPrueba: () => `Simular corrección de ${tarea}`,
    botonReal: (envia) => (envia ? `Corregir ${tarea} y mandar feedback` : `Corregir ${tarea} y dejarlas para revisar`),
    alerta: (envia) => (envia
      ? "Se llama al modelo (gasta API), las notas quedan guardadas y cada alumno recibe su feedback por correo."
      : "Se llama al modelo (gasta API) y las notas quedan guardadas. No sale ningún correo: las correcciones "
        + "quedan abajo para leerlas, editarlas y mandarlas."),
    confirmar: (a) => (a.no_enviar
      ? `Vas a corregir ${tarea} con GPT (gasta tokens) y guardar las notas. El feedback queda para revisarlo antes de mandarlo.`
      : `Vas a corregir ${tarea} con GPT y mandarle el feedback por correo a cada alumno. Son correos reales.`),
    despues: (d) => vistaRevision(d),
  },
  {
    id: "segunda", titulo: "Segunda oportunidad", flujo: "tareas.segunda", aparte: true,
    vista: (p, d) => vistaSegunda(d),
  },
];

let pestana = PESTANAS.find((p) => p.id === location.hash.slice(1)) || PESTANAS[0];

function irA(id) {
  pestana = PESTANAS.find((p) => p.id === id) || pestana;
  dibujar();
}

const rutaUrl = (ruta) => ruta.split("/").map(encodeURIComponent).join("/");
const urlArchivo = (ruta) => `/api/archivo/${encodeURIComponent(semestre)}/${rutaUrl(ruta)}`;
const carpetaEntregas = () => `tareas/data/entregas/${tarea}/`;
const rutaChequeo = () => `tareas/cache/chequeo_${tarea}.json`;
const rutaAsignacion = () => `${carpetaEntregas()}asignacion_${tarea}.csv`;
const rutaCorreos = () => `${carpetaEntregas()}correos_${tarea}.csv`;
const rutaFeedbackDe = (t) => `tareas/data/salidas/feedback_${t}.csv`;
const buscar = (ruta) => archivos.find((a) => a.ruta === ruta);
// Las columnas de correos_<T>.csv (modulos/tareas/asignacion.py).
const COLUMNAS_CORREOS = ["grupo_archivo", "alumno_nombre", "alumno_correo"];

async function actualizarArchivos() {
  archivos = await api(`/api/archivos/${encodeURIComponent(semestre)}`);
}

function htmlsDeLaTarea() {
  return archivos.filter((a) => a.ruta.startsWith(carpetaEntregas()) && a.ruta.endsWith(".html"))
    .map((a) => a.ruta.slice(carpetaEntregas().length)).filter((n) => !n.includes("/")).sort();
}

// ---------------------------------------------------------------- dónde va la tarea
//
// Sale de lo guardado en la nube, no del historial de trabajos. Qué deja cada
// paso (modulos/tareas/):
//   generar    -> salidas/feedback_<T>.csv, una fila por integrante; con pregunta si se generó
//   enviar     -> notas.csv (Flujo tarea, Item <T>): Enviado
//   recolectar -> notas.csv: Respondio
//   corregir   -> notas.csv: Nota

// { tarea, datos } con datos = los conteos, false si no se pudo leer, o undefined mientras carga.
let estadoTarea = { tarea: null, datos: undefined };
const zonaEstado = el("div");
const zonaPestanas = el("div");
// Si el paso elegido necesita uno anterior que no se ha hecho, lo dice aquí.
const zonaFalta = el("div");

async function leerTexto(ruta) {
  const r = await fetch(urlArchivo(ruta), { cache: "no-store" });
  if (r.status === 404) return "";
  if (!r.ok) throw new Error(String(r.status));
  return r.text();
}

/** El texto de un archivo y su etag, para guardarlo después sin pisar otra versión. */
async function leerConEtag(ruta) {
  // Si no está en la lista, se crea. Si la lista estaba vieja y sí existía, el
  // sitio rechaza la escritura (if-none-match) en vez de pisarlo.
  if (!buscar(ruta)) return { texto: "", etag: null };
  const r = await fetch(urlArchivo(ruta), { cache: "no-store" });
  if (r.status === 404) return { texto: "", etag: null };
  if (!r.ok) throw new Error(String(r.status));
  const etag = (r.headers.get("etag") || buscar(ruta)?.etag || "").replace(/"/g, "");
  return { texto: await r.text(), etag: etag || null };
}

/** Guarda un CSV. Si en la nube cambió desde que se leyó, el sitio responde 409 y no se pisa. Devuelve el etag nuevo. */
async function guardarCsv(ruta, texto, etag, detalle) {
  const r = await api(urlArchivo(ruta), {
    method: "PUT", body: texto, headers: {
      "content-type": "text/csv; charset=utf-8", ...conDetalle(detalle),
      ...(etag ? { "if-match": etag } : { "if-none-match": "*" }),
    },
  });
  return r?.etag || null;
}

const enCsv = (v) => (v || "").trim();

async function leerEstadoTarea(t) {
  const rutaFeedback = rutaFeedbackDe(t);
  const [notas, feedback] = await Promise.all([leerTexto("notas.csv"),
    buscar(rutaFeedback) ? leerTexto(rutaFeedback) : ""]);
  const datos = { generadas: 0, enviados: 0, primerEnvio: "", respondieron: 0, corregidas: 0, porMandar: 0 };
  if (feedback.trim()) {
    const { columnas, filas } = leerCsv(feedback);
    const [ip, ipend, ic] = ["pregunta", "feedback_pendiente", "alumno_correo"].map((c) => columnas.indexOf(c));
    datos.generadas = filas.filter((f) => enCsv(f[ip])).length;
    // Corregidas que esperan revisión antes de mandarse (corregir --no-enviar).
    if (ipend >= 0) datos.porMandar = filas.filter((f) => enCsv(f[ipend]) && enCsv(f[ic])).length;
  }
  if (notas.trim()) {
    const { columnas, filas } = leerCsv(notas);
    const [iF, iI, iE, iR, iN] = ["Flujo", "Item", "Enviado", "Respondio", "Nota"].map((c) => columnas.indexOf(c));
    for (const f of filas) {
      if ((f[iF] || "").trim() !== "tarea" || (f[iI] || "").trim().toUpperCase() !== t) continue;
      const enviado = (f[iE] || "").trim();
      if (enviado) {
        datos.enviados++;
        if (!datos.primerEnvio || enviado < datos.primerEnvio) datos.primerEnvio = enviado;
      }
      if ((f[iR] || "").trim()) datos.respondieron++;
      if ((f[iN] || "").trim()) datos.corregidas++;
    }
  }
  return datos;
}

/** Vuelve a leer el estado de la tarea elegida y redibuja su estado y sus pestañas. */
async function refrescarEstado() {
  const t = tarea;
  if (estadoTarea.tarea !== t) estadoTarea = { tarea: t, datos: undefined };
  pintarCabecera();
  let datos;
  try {
    datos = await leerEstadoTarea(t);
  } catch {
    datos = false;
  }
  if (tarea !== t) return; // cambiaron de tarea mientras se leía
  estadoTarea = { tarea: t, datos };
  pintarCabecera();
}

function ahoraTocaTarea(d) {
  if (!d.generadas) return { id: "generar", texto: `Generar las preguntas de ${tarea}` };
  if (!d.enviados) return { id: "enviar", texto: `Enviar las preguntas de ${tarea}` };
  const porCorregir = d.respondieron - d.corregidas;
  if (porCorregir > 0) {
    return { id: "corregir", texto: `Corregir ${porCorregir === 1 ? "la respuesta pendiente" : `las ${porCorregir} respuestas pendientes`} de ${tarea}`,
      motivo: "Simula primero para elegir a quién corregir." };
  }
  if (d.porMandar > 0) {
    return { id: "corregir", texto: `Revisar y mandar ${d.porMandar === 1 ? "la corrección pendiente"
      : `las ${d.porMandar} correcciones pendientes`} de ${tarea}`,
      motivo: "Las notas ya están guardadas; el feedback no ha salido." };
  }
  if (d.respondieron < d.enviados) {
    const faltan = d.enviados - d.respondieron;
    return { id: "recolectar", texto: `Recolectar las respuestas de ${tarea}`,
      motivo: `Faltan ${faltan} por recolectar.` };
  }
  return null;
}

const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

/** Las pestañas: los cuatro pasos con en qué va cada uno, y Segunda oportunidad aparte. */
function pestanasDeTarea(d) {
  const toca = d ? ahoraTocaTarea(d) : null;
  const detalle = {};
  const hecho = {};
  if (d) {
    const m = String(d.primerEnvio).match(/^\d{4}-(\d{2})-(\d{2})/);
    const porCorregir = d.respondieron - d.corregidas;
    detalle.generar = d.generadas ? plural(d.generadas, "pregunta", "preguntas") : "Ninguna todavía";
    detalle.enviar = d.enviados ? `A ${d.enviados}${m ? ` el ${m[2]}/${m[1]}` : ""}` : null;
    // Respondio se llena al recolectar: lo que no se ha recolectado no se sabe.
    detalle.recolectar = d.respondieron ? `${d.respondieron} de ${d.enviados} recolectadas` : null;
    detalle.corregir = porCorregir > 0 ? `${porCorregir} por corregir`
      : d.porMandar > 0 ? `${d.porMandar} por mandar`
        : d.corregidas ? plural(d.corregidas, "corregida", "corregidas") : null;
    hecho.generar = d.generadas > 0;
    hecho.enviar = d.enviados > 0;
    hecho.recolectar = d.enviados > 0 && d.respondieron >= d.enviados;
    hecho.corregir = d.corregidas > 0 && porCorregir === 0 && !d.porMandar;
  }
  const paso = (id, numero, titulo) => ({ id, numero, titulo, detalle: detalle[id], hecho: hecho[id], toca: toca?.id === id });
  return barraPestanas({
    etiqueta: `Pasos de ${tarea}`, actual: pestana.id, alElegir: irA, flujo: true,
    grupos: [
      { rotulo: `Pasos de ${tarea}`, flechas: true, pestanas: [
        paso("generar", 1, "Generar preguntas"), paso("enviar", 2, "Enviar preguntas"),
        paso("recolectar", 3, "Recolectar respuestas"), paso("corregir", 4, "Corregir"),
      ] },
      { rotulo: "Si hace falta", pestanas: [{ id: "segunda", titulo: "Segunda oportunidad" }] },
    ],
  });
}

/** La frase de arriba: en qué va la tarea, con sus números, y qué toca ahora. */
function lineaEstadoTarea(d) {
  if (d === undefined) return el("p", { class: "estado-curso" }, `${tarea}: leyendo en qué va…`);
  if (d === false) {
    return el("p", { class: "estado-curso" }, `${tarea}: no pude leer en qué va (notas.csv). Las pestañas funcionan igual.`);
  }
  const m = String(d.primerEnvio).match(/^\d{4}-(\d{2})-(\d{2})/);
  // Respondio se llena al recolectar: lo que no se ha recolectado no se sabe.
  const hechos = [
    d.generadas ? plural(d.generadas, "pregunta generada", "preguntas generadas") : null,
    d.enviados ? `enviadas a ${d.enviados}${m ? ` el ${m[2]}/${m[1]}` : ""}` : null,
    d.respondieron ? `${d.respondieron} ${d.respondieron === 1 ? "respuesta recolectada" : "respuestas recolectadas"}` : null,
    d.corregidas ? plural(d.corregidas, "corregida", "corregidas") : null,
  ].filter(Boolean);
  const toca = ahoraTocaTarea(d);
  const accion = toca ? toca.texto.charAt(0).toLowerCase() + toca.texto.slice(1) : null;
  return el("p", { class: "estado-curso" },
    el("strong", {}, `${tarea}: `), hechos.length ? `${hechos.join(", ")}. ` : "",
    toca
      ? ["Toca ", el("a", { href: `#${toca.id}`, onclick: (e) => { e.preventDefault(); irA(toca.id); } }, accion), ".",
        toca.motivo ? ` ${toca.motivo}` : ""]
      : "Cerrada: todos los que recibieron la pregunta respondieron y quedaron corregidos.");
}

function pintarCabecera() {
  const d = estadoTarea.tarea === tarea ? estadoTarea.datos : undefined;
  zonaEstado.replaceChildren(lineaEstadoTarea(d));
  zonaPestanas.replaceChildren(pestanasDeTarea(d || null));
  zonaFalta.replaceChildren(faltaPasoAnterior(d) || "");
}

/** El aviso de que el paso elegido llega antes de tiempo, o null. */
function faltaPasoAnterior(d) {
  if (!d) return null;
  if (pestana.id === "enviar" && !d.generadas) {
    return caja("aviso", `Todavía no hay preguntas generadas de ${tarea}: genéralas en el paso 1 antes de enviarlas.`);
  }
  if ((pestana.id === "recolectar" || pestana.id === "corregir") && !d.enviados) {
    return caja("aviso", `${tarea} todavía no se envía: no hay respuestas que ${pestana.id === "corregir" ? "corregir" : "recolectar"}.`);
  }
  if (pestana.id === "segunda" && !d.enviados) {
    return caja("aviso", `${tarea} todavía no se envía: la segunda oportunidad es para quienes no respondieron la primera.`);
  }
  return null;
}

// ---------------------------------------------------------------- historial

const historial = historialTrabajos({
  prefijo: "tareas.",
  // Los chequeos se piden solos al abrir la pestaña 1: listarlos taparía los
  // trabajos que sí importan.
  incluye: (t) => t.flujo.startsWith("tareas.") && t.flujo !== "tareas.chequeo",
  columna: ["Tarea", (a) => a.tarea ?? ""],
  alElegir: (t) => {
    const destino = document.getElementById("resultado");
    seguir(t.id, destino);
    destino.scrollIntoView({ behavior: "smooth", block: "start" });
  },
});

// Después de revisar la corrección en modo prueba: elegir a quién corregir de verdad.
function elegir(t) {
  // Segunda oportunidad en modo prueba: los borradores de los correos, para leerlos.
  if (t.flujo === "tareas.segunda" && t.argumentos.paso === "enviar" && t.prueba && t.estado === "terminado") {
    const ruta = `tareas/data/salidas/correos_segunda_oportunidad_${t.argumentos.tarea}.txt`;
    return el("a", { class: "descarga", href: `${urlArchivo(ruta)}?descargar` }, "Descargar los borradores");
  }
  if (t.flujo !== "tareas.corregir" || !t.prueba || t.estado !== "terminado") return null;
  const tareaRevisada = t.argumentos.tarea;
  // El semestre y la lista son los de esta revisión, no los del selector. Las
  // correcciones quedan para revisarlas antes de mandarlas (vistaRevision).
  return elegirCandidatos({
    semestre: t.semestre, ruta: `tareas/cache/candidatos_${tareaRevisada}_${t.id}.json`, verbo: "Corregir",
    mandaFeedback: false,
    alProcesar: async (solo) => {
      const id = await pedirTrabajo(t.semestre, "tareas.corregir",
        { tarea: tareaRevisada, prueba: false, no_enviar: true, solo });
      await seguir(id, document.getElementById("resultado"));
    },
  });
}

function seguir(id, destino) {
  return seguirTrabajo(id, destino, { extra: elegir, alTerminar: async () => {
    historial.dibujar(semestre);
    // Generar deja feedback_<T>.csv: hay que volver a listar antes de leer el estado.
    await actualizarArchivos().catch(() => {});
    refrescarEstado();
    // Corregir y mandar cambian qué correcciones esperan revisión.
    recargarRevision();
  } });
}

// ---------------------------------------------------------------- selector de tarea

function selectorTarea() {
  const opciones = tareasConocidas(archivos);
  const texto = el("input", { type: "text", size: 6, pattern: "T\\d{1,2}" });
  // "t2", "Tarea 3" y "3" valen como T2 y T3; lo demás se rechaza en voz alta,
  // para que nadie crea que está trabajando sobre otra tarea.
  const cambiar = (t) => {
    const m = String(t).trim().match(/^(?:t|tarea)?\s*(\d{1,2})$/i);
    const valor = m ? `T${Number(m[1])}` : "";
    if (!valor || valor === "T0") {
      texto.value = tarea;
      texto.setCustomValidity("Escribe la tarea como T1, T2…");
      texto.reportValidity();
      return;
    }
    texto.setCustomValidity("");
    texto.value = valor;
    if (valor === tarea) return;
    tarea = valor;
    dibujar();
  };
  texto.addEventListener("input", () => texto.setCustomValidity(""));
  texto.addEventListener("change", () => cambiar(texto.value));
  if (!opciones.length) {
    texto.value = tarea;
    return el("label", { class: "campo" }, "Tarea (ej. T1)", texto);
  }
  const nueva = !opciones.includes(tarea);
  const sel = el("select", {}, [...opciones, "Nueva..."].map((o) =>
    el("option", { value: o, selected: nueva ? o === "Nueva..." : o === tarea }, o)));
  texto.value = nueva ? tarea : `T${Math.max(...opciones.map((o) => Number(o.slice(1)))) + 1}`;
  sel.addEventListener("change", () => {
    if (sel.value === "Nueva...") { texto.hidden = false; texto.focus(); cambiar(texto.value); }
    else cambiar(sel.value);
  });
  texto.hidden = !nueva;
  return el("div", { class: "fila-campos" }, el("label", { class: "campo" }, "Tarea", sel),
    el("label", { class: "campo" }, texto));
}

// ---------------------------------------------------------------- chequeo

const kpi = (etiqueta, valor) => el("div", { class: "kpi" },
  el("div", { class: "etiqueta" }, etiqueta), el("div", { class: "valor" }, valor));

/** La lista de alumnos, [nombre, correo] por nombre, para elegir a mano un correo. */
async function leerRoster() {
  const { columnas, filas } = leerCsv(await leerTexto("alumnos.csv"));
  const [iN, iC] = ["Nombre", "Correo"].map((c) => columnas.indexOf(c));
  return filas.map((f) => [enCsv(f[iN]), enCsv(f[iC]).toLowerCase()]).filter(([, c]) => c.includes("@"))
    .sort((a, b) => a[0].localeCompare(b[0], "es"));
}

/**
 * El correo de un integrante. El que no calzó con la lista de alumnos se elige
 * aquí, entre los parecidos o en la lista completa; uno que calzó mal se puede
 * cambiar. Lo elegido va a correos_<T>.csv, que leen generar y enviar.
 */
function celdaCorreo(g, i, correosSel, roster) {
  const automatico = i.correo && !i.correo_a_mano ? i.correo.toLowerCase() : "";
  const selector = () => {
    const sel = el("select", { class: "elegir-correo", "aria-label": `Correo de ${i.nombre}` },
      el("option", { value: "" }, i.correo_a_mano ? "Sin correo (quitar lo elegido)" : "Elegir de la lista de alumnos…"),
      i.candidatos.length ? el("optgroup", { label: "Parecidos" },
        i.candidatos.map(([n, c, sim]) => el("option", { value: c.toLowerCase() }, `${n} · ${c} (parecido ${sim})`))) : null,
      el("optgroup", { label: "Todos los alumnos" }, roster.map(([n, c]) =>
        el("option", { value: c, selected: c === (i.correo || "").toLowerCase() }, `${n} · ${c}`))));
    correosSel.push({ archivo: g.archivo, nombre: i.nombre, sel, automatico });
    return sel;
  };
  if (!i.correo) {
    return el("div", {}, el("span", { class: "falta-correo" }, "No calzó con la lista de alumnos"),
      i.candidatos.length ? null : el("div", { class: "nota-pie" }, "Ningún parecido razonable: búscalo en la lista."),
      selector());
  }
  if (i.correo_a_mano) return el("div", {}, selector(), el("div", { class: "nota-pie" }, "Elegido a mano"));
  const zona = el("div", {}, el("code", {}, i.correo), " ");
  zona.append(el("button", { class: "enlace", type: "button", title: "Si calzó con otro alumno",
    onclick: () => zona.replaceChildren(selector()) }, "cambiar"));
  return zona;
}

function grupoChequeo(g, selects, correosSel, roster) {
  // El mismo HTML dos veces (o subido por dos integrantes): generar lo salta.
  if (g.identico_a) {
    return el("details", {},
      el("summary", {}, `⊘ ${g.archivo} — igual a ${g.identico_a}`),
      el("div", { class: "contenido" }, caja("info",
        `Tiene el mismo contenido que ${g.identico_a}: las preguntas se generan una sola vez, con ese archivo.`)));
  }
  let icono, resumen;
  if (g.bloqueo.length) [icono, resumen] = ["❌", "se va a saltar"];
  else if (g.sin_roles || g.integrantes.some((i) => !i.correo)) [icono, resumen] = ["⚠️", "pide revisión"];
  else [icono, resumen] = ["✅", `${g.integrantes.length} integrantes`];

  const cortes = Object.entries(g.secciones)
    .map(([n, c]) => `P${n}: ${c.toLocaleString("es-CL")} car.`).join(" · ");
  const contenido = [
    g.fuente !== g.archivo ? caja("info", `El HTML viene sin código: se lee ${g.fuente}.`) : null,
    el("p", { class: "nota-pie" }, cortes),
  ];
  if (g.bloqueo.length) {
    contenido.push(caja("aviso", el("div", {}, "No se llama al modelo por esto:",
      el("ul", {}, g.bloqueo.map((m) => el("li", {}, m))))));
  } else {
    contenido.push(el("p", { class: "nota-pie" }, `Integrantes según: ${g.origen_integrantes}`));
    if (g.sin_roles) {
      contenido.push(caja("aviso", "El grupo no declaró quién hizo qué: la pregunta de cada integrante se "
        + "asignó al azar. Se puede cambiar aquí."));
    }
    contenido.push(el("div", { class: "integrantes" }, g.integrantes.map((i) => {
      const asignada = g.asignacion[i.nombre];
      let pregunta = null;
      if (asignada) {
        pregunta = el("select", { "aria-label": `Pregunta de ${i.nombre}` },
          ["P1", "P2", "P3", "P4"].map((o) => el("option", { value: o, selected: o === asignada }, o)));
        selects.push([g.archivo, i.nombre, pregunta]);
      }
      return el("div", { class: "integrante" },
        el("strong", {}, i.nombre),
        celdaCorreo(g, i, correosSel, roster),
        pregunta || el("span"));
    })));
  }
  return el("details", { open: g.bloqueo.length > 0 || g.sin_roles },
    el("summary", {}, `${icono} ${g.archivo} — ${resumen}`),
    el("div", { class: "contenido" }, contenido));
}

async function guardarAsignacion(selects) {
  // Igual que asignacion.escribir(): lo que ya estaba elegido a mano, más lo
  // que muestra cada selector, en orden por grupo y nombre.
  const elegido = new Map();
  const previo = buscar(rutaAsignacion());
  if (previo) {
    const { columnas, filas } = leerCsv(await (await fetch(urlArchivo(rutaAsignacion()), { cache: "no-store" })).text());
    const [ig, ia, ip] = ["grupo_archivo", "alumno_nombre", "pregunta_tarea"].map((c) => columnas.indexOf(c));
    for (const f of filas) {
      const p = (f[ip] || "").trim().toUpperCase();
      if (f[ig]?.trim() && f[ia]?.trim() && ["P1", "P2", "P3", "P4"].includes(p)) {
        elegido.set(JSON.stringify([f[ig].trim(), f[ia].trim()]), p);
      }
    }
  }
  for (const [archivo, nombre, sel] of selects) elegido.set(JSON.stringify([archivo, nombre]), sel.value);
  const filas = [...elegido.entries()].map(([k, p]) => [...JSON.parse(k), p])
    .sort((a, b) => (a[0] === b[0] ? (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0) : a[0] < b[0] ? -1 : 1));
  const texto = escribirCsv({ columnas: ["grupo_archivo", "alumno_nombre", "pregunta_tarea"], filas,
    formato: { sep: ",", eol: "\r\n" } });
  await api(urlArchivo(rutaAsignacion()), {
    method: "PUT", body: texto, headers: {
      "content-type": "text/csv; charset=utf-8",
      ...conDetalle(`Eligió a mano las preguntas de ${tarea} (${filas.length} alumnos)`),
      // Sin pisar una asignación que otra persona guardó mientras tanto.
      ...(previo ? { "if-match": previo.etag } : { "if-none-match": "*" }),
    },
  });
}

/** Guarda en correos_<T>.csv lo elegido en los selectores de correo. Devuelve cuántos cambiaron. */
async function guardarCorreos(correosSel) {
  const ruta = rutaCorreos();
  const { texto, etag } = await leerConEtag(ruta);
  const elegido = new Map();
  if (texto.trim()) {
    const { columnas, filas } = leerCsv(texto);
    const [ig, ia, ic] = COLUMNAS_CORREOS.map((c) => columnas.indexOf(c));
    for (const f of filas) {
      if (enCsv(f[ig]) && enCsv(f[ia]) && enCsv(f[ic]).includes("@")) {
        elegido.set(JSON.stringify([enCsv(f[ig]), enCsv(f[ia])]), enCsv(f[ic]).toLowerCase());
      }
    }
  }
  let cambios = 0;
  for (const { archivo, nombre, sel, automatico } of correosSel) {
    const k = JSON.stringify([archivo, nombre]);
    // Elegir el mismo correo con que ya calzaba no es una elección a mano.
    const ahora = sel.value !== automatico ? sel.value : "";
    if (ahora === (elegido.get(k) || "")) continue;
    if (ahora) elegido.set(k, ahora);
    else elegido.delete(k);
    cambios++;
  }
  if (!cambios) return 0;
  const filas = [...elegido.entries()].map(([k, c]) => [...JSON.parse(k), c])
    .sort((a, b) => (a[0] === b[0] ? a[1].localeCompare(b[1], "es") : a[0] < b[0] ? -1 : 1));
  await guardarCsv(ruta, escribirCsv({ columnas: COLUMNAS_CORREOS, filas, formato: { sep: ",", eol: "\r\n" } }),
    etag, `Eligió a mano el correo de ${cambios} integrante(s) de ${tarea}`);
  return cambios;
}

/** Qué material del curso va a ver el modelo al generar (modulos/tareas/contexto.py). */
function lineaContexto(c) {
  if (!c) return null; // chequeo guardado antes de que existiera este dato
  const enlace = el("a", { href: "/datos#datos/contexto" }, "Configuración › Tareas › Contexto");
  if (!c.activo) return el("p", { class: "nota-pie" }, "Contexto del curso: apagado.");
  if (!c.archivos.length) {
    return caja("info", el("span", {}, "Sin contexto del curso (", enlace, ")."));
  }
  return el("p", { class: "nota-pie" }, `Contexto del curso: ${c.archivos.length} archivo(s), `
    + `${Math.round(c.caracteres / 1000)} mil caracteres (`, enlace, ").");
}

function dibujarChequeo(informe, destino, cuando, roster = []) {
  const grupos = informe.grupos;
  if (!grupos.length) {
    destino.replaceChildren(caja("aviso", "No hay entregas que revisar."));
    return;
  }
  const activos = grupos.filter((g) => !g.bloqueo.length);
  const aGenerar = activos.reduce((n, g) => n + g.integrantes.filter((i) => i.correo).length, 0);
  const sinCorreo = activos.reduce((n, g) => n + g.integrantes.filter((i) => !i.correo).length, 0);
  const selects = [];
  const correosSel = [];
  const mensaje = el("div");
  const duplicados = informe.duplicados || [];
  const partes = [
    el("p", { class: "nota-pie" }, `Revisado el ${cuando} · `,
      el("button", { class: "enlace", type: "button", onclick: () => revisar(destino) }, "Volver a revisar")),
    lineaContexto(informe.contexto),
    informe.desempacados?.length ? caja("info", `Se abrieron los .rar: ${informe.desempacados.join(", ")}.`) : null,
    ...(informe.rar_omitidos || []).map((o) => caja("aviso", o)),
    el("div", { class: "kpis", style: "grid-template-columns: repeat(3, 1fr)" },
      kpi("Preguntas que se generarían", aGenerar), kpi("Sin correo, a resolver", sinCorreo),
      kpi("Grupos que se saltarían", grupos.length - activos.length)),
    // Pasó en T2 de 2026-2: un alumno subió una versión propia además de la de su grupo.
    duplicados.length ? caja("aviso", el("div", {},
      "Aparecen en más de una entrega. Reciben una sola pregunta, la de la primera entrega:",
      el("ul", {}, duplicados.map((d) => el("li", {}, `${d.nombre} (${d.correo}): ${d.archivos.join(" y ")}`))))) : null,
    ...grupos.map((g) => grupoChequeo(g, selects, correosSel, roster)),
  ].filter(Boolean);
  if (activos.some((g) => g.integrantes.length)) {
    const boton = el("button", { class: "descarga", type: "button" }, "Guardar lo elegido");
    boton.addEventListener("click", async () => {
      boton.disabled = true;
      try {
        if (selects.length) await guardarAsignacion(selects);
        const cambios = correosSel.length ? await guardarCorreos(correosSel) : 0;
        await actualizarArchivos();
        if (cambios) {
          // Se vuelve a revisar para ver los correos elegidos en su lugar.
          await revisar(destino);
          return;
        }
        mensaje.replaceChildren(caja(selects.length ? "exito" : "info", selects.length
          ? `Guardado en asignacion_${tarea}.csv. Generar va a usar esto.` : "No había nada nuevo que guardar."));
      } catch (e) {
        mensaje.replaceChildren(caja("aviso", `No pude guardar: ${e.message}`));
      } finally {
        boton.disabled = false;
      }
    });
    partes.push(el("p", { class: "nota-pie" }, "Las preguntas asignadas y los correos elegidos a mano los usan "
      + "Generar y Enviar."), el("div", { class: "acciones" }, boton), mensaje);
  }
  if (informe.sin_entrega.length) {
    partes.push(el("details", {},
      el("summary", {}, `Del roster (${informe.total_roster}), quedan sin pregunta ${informe.sin_entrega.length}`),
      el("div", { class: "contenido" },
        el("p", { class: "nota-pie" }, "Incluye al equipo docente si está en la lista."),
        el("ul", {}, informe.sin_entrega.map((n) => el("li", {}, n))))));
  }
  destino.replaceChildren(...partes);
}

async function mostrarChequeo(destino) {
  const info = buscar(rutaChequeo());
  const [informe, roster] = await Promise.all([
    fetch(urlArchivo(rutaChequeo()), { cache: "no-store" }).then((r) => r.text()).then(JSON.parse),
    leerRoster().catch(() => [])]);
  const cuando = new Date(info.subido).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" });
  dibujarChequeo(informe, destino, cuando, roster);
  return informe;
}

// Los HTML que salieron de un .rar y ya se mostraron, como "T2/Grupo3.html".
const rarsVistos = new Set();

/** Pide un chequeo al motor y lo dibuja cuando termina. */
async function revisar(destino) {
  const tareaPedida = tarea;
  destino.replaceChildren(caja("info", "Revisando las entregas…"));
  try {
    const id = await pedirTrabajo(semestre, "tareas.chequeo", { tarea: tareaPedida });
    const salida = el("div", { hidden: true });
    destino.append(salida);
    await seguirTrabajo(id, salida, {
      alTerminar: async (t) => {
        if (tarea !== tareaPedida) return; // cambiaron de tarea mientras corría
        if (t.estado !== "terminado") { salida.hidden = false; return; }
        await actualizarArchivos();
        // Sin esto, un chequeo que termina sin dejar su archivo dejaba
        // "Revisando…" para siempre (y un error en la consola).
        if (!buscar(rutaChequeo())) {
          destino.replaceChildren(caja("aviso", el("span", {},
            "La revisión terminó, pero no dejó su resultado en la nube. ",
            el("button", { class: "enlace", type: "button", onclick: () => revisar(destino) }, "Volver a revisar"))));
          return;
        }
        const informe = await mostrarChequeo(destino);
        // Los .rar que se abrieron son entregas nuevas: la lista de arriba tiene
        // que mostrarlas. Una sola vez por .rar: si su HTML no alcanzó a quedar
        // en la nube, el chequeo siguiente lo vuelve a abrir, y redibujar de
        // nuevo pediría otro chequeo, y otro.
        const nuevos = (informe.desempacados || []).filter((n) => !rarsVistos.has(`${tareaPedida}/${n}`));
        nuevos.forEach((n) => rarsVistos.add(`${tareaPedida}/${n}`));
        if (nuevos.length && pestana.id === "generar") dibujar();
      },
    });
  } catch (e) {
    destino.replaceChildren(caja("aviso", `No pude revisar las entregas: ${e.message}`));
  }
}

/**
 * El chequeo guardado sirve mientras no hayan cambiado las entregas, la
 * asignación ni la lista de alumnos. Si cambiaron, se vuelve a pedir.
 */
function chequeoAlDia() {
  const guardado = buscar(rutaChequeo());
  if (!guardado) return false;
  const influyen = archivos.filter((a) => a.ruta.startsWith(carpetaEntregas()) || a.ruta === "alumnos.csv"
    || a.ruta.startsWith("tareas/data/clases/"));
  return influyen.every((a) => a.subido <= guardado.subido);
}

// ---------------------------------------------------------------- pestañas

function vistaGenerar(destino) {
  const htmls = htmlsDeLaTarea();
  // La página sube los .rar sin abrir; el chequeo los abre.
  const rars = archivos.filter((a) => a.ruta.startsWith(carpetaEntregas()) && /\.rar$/i.test(a.ruta));
  const partes = [];
  const casillas = htmls.map((n) => el("input", { type: "checkbox", checked: true, value: n }));
  const boton = el("button", { class: "primario", type: "button", disabled: !htmls.length },
    `Generar preguntas de ${tarea}`);
  const actualizar = () => { boton.disabled = !casillas.some((c) => c.checked); };
  for (const c of casillas) c.addEventListener("change", actualizar);

  if (!htmls.length && !rars.length) {
    partes.push(caja("aviso", el("span", {}, `No hay entregas de ${tarea}. Se suben en `,
      el("a", { href: "/datos#datos/entregas" }, "Configuración › Tareas › Entregas"), ".")));
  } else {
    const todos = (v) => { for (const c of casillas) c.checked = v; actualizar(); };
    if (htmls.length) partes.push(el("details", {},
      el("summary", {}, `Entregas a procesar (${htmls.length})`),
      el("div", { class: "contenido" },
        el("div", { class: "acciones" },
          el("button", { class: "enlace", type: "button", onclick: () => todos(true) }, "Todos"),
          el("button", { class: "enlace", type: "button", onclick: () => todos(false) }, "Ninguno")),
        el("div", { class: "lista-casillas" }, htmls.map((n, i) =>
          el("label", { class: "interruptor" }, casillas[i], n))))));

    const chequeo = el("div");
    partes.push(el("hr"), el("h4", {}, "Estado de las entregas"),
      chequeo);
    if (chequeoAlDia()) {
      mostrarChequeo(chequeo).catch(() => revisar(chequeo));
    } else {
      revisar(chequeo);
    }
  }

  partes.push(
    el("p", { class: "nota-pie" }, "Los nombres que no calcen con Configuración › Tareas › Alumnos quedan sin correo "
      + "hasta que se elija en el estado de las entregas."),
    el("div", { class: "form-trabajo" }, boton,
      el("span", { class: "costo" }, "Una llamada al modelo por alumno. No manda correos.")));

  boton.addEventListener("click", async () => {
    const elegidos = casillas.filter((c) => c.checked).map((c) => c.value);
    boton.disabled = true;
    try {
      const id = await pedirTrabajo(semestre, "tareas.generar", { tarea, archivos: elegidos });
      await seguir(id, destino);
      historial.dibujar(semestre);
    } catch (e) {
      destino.replaceChildren(caja("aviso", `No pude pedir el trabajo: ${e.message}`));
    } finally {
      actualizar();
    }
  });
  return partes;
}

// ---------------------------------------------------------------- segunda oportunidad

/**
 * Una pregunta nueva para quien recibió la primera y no respondió. Dos pasos:
 * preparar (el modelo genera las preguntas; no sale ningún correo) y enviar
 * (en modo prueba solo arma los borradores). Después, recolectar y corregir
 * funcionan como siempre, contra la pregunta nueva.
 */
function vistaSegunda(destino) {
  const rutaCsv = `tareas/data/salidas/segunda_oportunidad_${tarea}.csv`;
  const vista = el("div");
  if (buscar(rutaCsv)) {
    fetch(urlArchivo(rutaCsv), { cache: "no-store" }).then((r) => r.text()).then((texto) => {
      const { columnas, filas } = leerCsv(texto);
      const col = (n) => columnas.indexOf(n);
      const enviados = filas.filter((f) => f[col("message_id")]).length;
      vista.replaceChildren(
        el("p", { class: "nota-pie" }, `${filas.length} alumnos · ${enviados} ya recibieron su pregunta nueva`),
        el("div", { class: "tabla-envoltura editor-envoltura" }, el("table", {},
          el("thead", {}, el("tr", {}, ["Alumno", "Parte", "Pregunta nueva", "Enviada"].map((c) => el("th", {}, c)))),
          el("tbody", {}, filas.map((f) => el("tr", {},
            el("td", {}, f[col("nombre")]), el("td", {}, f[col("pregunta_tarea")]),
            el("td", {}, el("div", { class: "celda-lectura" }, f[col("pregunta")] || "(sin preparar)")),
            el("td", {}, f[col("enviado")] ? fechaCorta(new Date(f[col("enviado")])) : "—")))))),
        el("div", { class: "acciones" },
          el("a", { class: "descarga", href: `${urlArchivo(rutaCsv)}?descargar` }, "Descargar el CSV")));
    }).catch(() => vista.replaceChildren(caja("aviso", "No pude leer la lista de la segunda oportunidad.")));
  } else {
    vista.replaceChildren(caja("info", `Todavía no hay segunda oportunidad preparada para ${tarea}.`));
  }

  const pedir = async (argumentos, boton) => {
    boton.disabled = true;
    try {
      const id = await pedirTrabajo(semestre, "tareas.segunda", { tarea, ...argumentos });
      await seguir(id, destino);
      historial.dibujar(semestre);
    } catch (e) {
      destino.replaceChildren(caja("aviso", `No pude pedir el trabajo: ${e.message}`));
    } finally {
      boton.disabled = false;
    }
  };
  const preparar = el("button", { class: "primario", type: "button" }, `Preparar preguntas nuevas de ${tarea}`);
  preparar.addEventListener("click", () => pedir({ paso: "preparar" }, preparar));

  const prueba = el("input", { type: "checkbox", checked: true });
  const alerta = el("div");
  const enviar = el("button", { class: "primario", type: "button" });
  // Solo textos: qué se manda al pedir el trabajo se decide en el clic.
  const actualizar = () => {
    alerta.replaceChildren(prueba.checked ? "" : el("div", { class: "nota-real" }, el("strong", {}, "Envío real: quienes "
      + "no respondieron reciben la pregunta nueva por correo. No se puede deshacer.")));
    enviar.classList.toggle("real", !prueba.checked);
    enviar.textContent = prueba.checked ? `Ver los borradores de ${tarea}`
      : `Enviar la pregunta nueva de ${tarea}`;
  };
  prueba.addEventListener("change", actualizar);
  enviar.addEventListener("click", async () => {
    if (!prueba.checked && !await confirmar(`Vas a mandar la pregunta nueva de ${tarea} a quienes no respondieron la `
      + "primera. Son correos reales. Quien ya la recibió no la recibe de nuevo.\n\n¿Confirmas?", enviar.textContent,
    "real")) return;
    pedir({ paso: "enviar", prueba: prueba.checked }, enviar);
  });
  actualizar();

  return [
    el("p", {}, "Una pregunta nueva para quienes recibieron la primera y no respondieron, una vez vencido el plazo."),
    el("h4", {}, "1 · Preparar"),
    el("p", { class: "nota-pie" }, "Una llamada al modelo por alumno. No manda correos."),
    el("div", { class: "form-trabajo" }, preparar),
    vista,
    el("h4", {}, "2 · Enviar"),
    el("div", { class: "form-trabajo" },
      el("label", { class: "interruptor" }, prueba, "Solo ver los borradores"), enviar),
    alerta,
  ];
}

function vistaPaso(p, destino) {
  const prueba = p.prueba ? el("input", { type: "checkbox", checked: true }) : null;
  const noEnviar = p.noEnviar ? el("input", { type: "checkbox", checked: Boolean(p.noEnviarMarcado) }) : null;
  // "Sin mandar el feedback" solo cambia algo corriendo de verdad: en la
  // simulación no sale nada igual. Se oculta para que no parezca otro modo seguro.
  const campoNoEnviar = noEnviar ? el("label", { class: "interruptor" }, noEnviar, p.noEnviar) : null;
  const alerta = el("div");
  const boton = el("button", { class: "primario", type: "button" });

  // Solo textos y avisos: qué se manda al pedir el trabajo se decide en el clic.
  const actualizar = () => {
    const real = prueba && !prueba.checked;
    const envia = real && !(noEnviar && noEnviar.checked);
    if (campoNoEnviar) campoNoEnviar.hidden = !real;
    alerta.replaceChildren(real ? el("div", { class: "nota-real" }, el("strong", {}, p.alerta(envia))) : "");
    boton.classList.toggle("real", Boolean(real));
    boton.textContent = !prueba ? p.boton() : real ? p.botonReal(envia) : p.botonPrueba();
  };
  prueba?.addEventListener("change", actualizar);
  noEnviar?.addEventListener("change", actualizar);

  boton.addEventListener("click", async () => {
    const argumentos = { tarea, prueba: prueba ? prueba.checked : true };
    if (noEnviar) argumentos.no_enviar = noEnviar.checked;
    if (p.confirmar && prueba && !prueba.checked
      && !await confirmar(`${p.confirmar(argumentos)}\n\n¿Confirmas?`, boton.textContent, "real")) return;
    boton.disabled = true;
    try {
      const id = await pedirTrabajo(semestre, p.flujo, argumentos);
      await seguir(id, destino);
      historial.dibujar(semestre);
    } catch (e) {
      destino.replaceChildren(caja("aviso", `No pude pedir el trabajo: ${e.message}`));
    } finally {
      boton.disabled = false;
    }
  });

  actualizar();
  return [
    p.texto ? el("p", {}, p.texto) : null,
    p.info ? caja("info", p.info) : null,
    p.nota ? el("p", { class: "nota-pie" }, p.nota) : null,
    el("div", { class: "form-trabajo" },
      prueba ? el("label", { class: "interruptor" }, prueba, p.prueba) : null,
      campoNoEnviar,
      boton),
    alerta,
  ];
}

// ---------------------------------------------------------------- enviar

const MINUTOS_POR_DEFECTO = 20; // el de modulos/tareas/enviar.py
// En un envío programado, cuántos minutos después del plazo se recolecta y se
// corrige. "Hasta las 10:20" incluye todo ese minuto, y el correo tarda en llegar.
const RECOLECTAR_DESPUES = 2;
const CORREGIR_DESPUES = 3;

const sumarMinutos = (d, m) => new Date(d.getTime() + m * 60_000);
const alMinuto = (d) => { const x = new Date(d); x.setSeconds(0, 0); return x; };

/** "2026-11-13T10:00", para un <input type="datetime-local">, en la hora de quien mira. */
function valorLocal(d) {
  const dos = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}T${dos(d.getHours())}:${dos(d.getMinutes())}`;
}

/**
 * Las preguntas y pautas generadas, para leerlas y corregirlas antes de enviar.
 * Solo las que no han salido: una pregunta enviada ya no se cambia. Devuelve
 * el nodo y `guardar()`, que enviar llama antes de pedir el trabajo para que no
 * se pierda lo editado.
 */
function editorPreguntas() {
  const nodo = el("div");
  const ruta = rutaFeedbackDe(tarea);
  let guardar = async () => {};
  if (!buscar(ruta)) return { nodo, guardar: () => guardar() };
  nodo.append(el("p", { class: "cargando" }, "Cargando las preguntas…"));
  (async () => {
    const leido = await leerConEtag(ruta);
    let etag = leido.etag;
    const csv = leerCsv(leido.texto);
    const col = (n) => csv.columnas.indexOf(n);
    const [iN, iG, iP, iQ, iPa, iM] = ["alumno_nombre", "grupo_archivo", "pregunta_tarea", "pregunta", "pauta",
      "message_id"].map(col);
    const porEnviar = csv.filas.filter((f) => enCsv(f[iQ]) && !enCsv(f[iM]));
    if (!porEnviar.length) { nodo.replaceChildren(); return; }
    // generar deja un aviso cuando la pregunta cita código que no está en la
    // entrega (venía del material del curso en T2 de 2026-2).
    const iA = col("aviso");
    const avisoDe = (f) => (iA >= 0 ? enCsv(f[iA]).trim() : "");
    const conAviso = porEnviar.filter(avisoDe).length;
    const editadas = new Set();
    const boton = el("button", { class: "secundario", type: "button", disabled: true }, "Guardar cambios");
    const mensaje = el("div");
    guardar = async () => {
      if (!editadas.size) return;
      const n = editadas.size;
      etag = await guardarCsv(ruta, escribirCsv(csv), etag,
        `Corrigió a mano ${n === 1 ? "una pregunta" : `${n} preguntas`} de ${tarea} antes de enviarla${n === 1 ? "" : "s"}`) || etag;
      editadas.clear();
      boton.disabled = true;
      mensaje.replaceChildren(caja("exito", "Guardado. Enviar manda lo que quedó escrito."));
    };
    boton.addEventListener("click", async () => {
      boton.disabled = true;
      try {
        await guardar();
      } catch (e) {
        mensaje.replaceChildren(caja("aviso", `No pude guardar: ${e.message}`));
        boton.disabled = false;
      }
    });
    const campo = (f, i, etiqueta, filas) => {
      const area = el("textarea", { rows: filas }, f[i] || "");
      area.addEventListener("input", () => {
        f[i] = area.value;
        // Quien la corrigió a mano ya la revisó: el aviso de generar se borra.
        if (i === iQ && iA >= 0) f[iA] = "";
        editadas.add(f);
        boton.disabled = false;
        mensaje.replaceChildren();
      });
      return el("label", { class: "campo campo-ancho" }, etiqueta, area);
    };
    nodo.replaceChildren(el("details", { class: "preguntas-tarea" },
      el("summary", {}, `Leer o corregir las preguntas antes de enviarlas (${porEnviar.length})`),
      el("div", { class: "contenido" },
        el("p", { class: "nota-pie" }, "El alumno recibe la pregunta. La pauta no la ve: es lo que usa el modelo al corregir."),
        conAviso ? caja("aviso", `${conAviso} pregunta(s) citan código que no está en la entrega. Revísalas antes de enviar.`) : "",
        ...porEnviar.map((f) => el("details", { class: "candidato", ...(avisoDe(f) ? { open: "" } : {}) },
          el("summary", {}, el("strong", {}, f[iN]), " ",
            el("span", { class: "tenue" }, [f[iP], f[iG]].filter(Boolean).join(" · ")),
            avisoDe(f) ? el("span", { class: "tenue" }, " · revisar") : ""),
          el("div", { class: "contenido" }, avisoDe(f) ? caja("aviso", `La pregunta ${avisoDe(f)}.`) : "",
            campo(f, iQ, "Pregunta", 5), campo(f, iPa, "Pauta", 7)))),
        el("div", { class: "acciones" }, boton), mensaje)));
  })().catch((e) => nodo.replaceChildren(caja("aviso", `No pude leer las preguntas generadas (${e.message}).`)));
  return { nodo, guardar: () => guardar() };
}

/**
 * A quién le va a llegar la pregunta en este envío, o null si es a todos.
 * Igual que modulos/tareas/enviar.py: las filas con pregunta que no han salido,
 * con el correo de la fila o el elegido a mano en correos_<T>.csv. Si ya salió
 * alguna, el envío es para un grupo chico (un alumno recuperado, por ejemplo) y
 * la recolección y la corrección programadas tienen que quedarse en ese grupo.
 */
async function correosDelEnvio(t) {
  const { columnas, filas } = leerCsv(await leerTexto(rutaFeedbackDe(t)));
  const [iN, iG, iQ, iC, iM] = ["alumno_nombre", "grupo_archivo", "pregunta", "alumno_correo", "message_id"]
    .map((c) => columnas.indexOf(c));
  const conPregunta = filas.filter((f) => enCsv(f[iQ]));
  if (!conPregunta.some((f) => enCsv(f[iM]))) return null;
  const elegidos = new Map();
  const texto = await leerTexto(`tareas/data/entregas/${t}/correos_${t}.csv`);
  if (texto.trim()) {
    const c = leerCsv(texto);
    const [ig, ia, ic] = COLUMNAS_CORREOS.map((n) => c.columnas.indexOf(n));
    for (const f of c.filas) {
      const nombre = enCsv(f[ia]).split(/\s+/).filter(Boolean).join(" ").toLowerCase();
      if (enCsv(f[ig]) && nombre && enCsv(f[ic]).includes("@")) {
        elegidos.set(JSON.stringify([enCsv(f[ig]).trim(), nombre]), enCsv(f[ic]).trim().toLowerCase());
      }
    }
  }
  const correos = new Set();
  for (const f of conPregunta.filter((x) => !enCsv(x[iM]))) {
    const nombre = enCsv(f[iN]).split(/\s+/).filter(Boolean).join(" ").toLowerCase();
    const correo = enCsv(f[iC]).trim().toLowerCase() || elegidos.get(JSON.stringify([enCsv(f[iG]).trim(), nombre])) || "";
    if (correo.includes("@")) correos.add(correo);
  }
  return [...correos];
}

/**
 * Enviar: con cuántos minutos tienen para responder y, si se quiere, a qué
 * hora. Un envío programado deja también agendadas la recolección y la
 * corrección (sin mandar el feedback), para el minuto en que vence el plazo.
 */
function vistaEnviar(p, destino) {
  const editor = editorPreguntas();
  const prueba = el("input", { type: "checkbox", checked: true });
  const minutos = el("input", { type: "number", min: 1, max: 1440, step: 1, value: MINUTOS_POR_DEFECTO,
    "aria-label": "Minutos para responder" });
  const programar = el("input", { type: "checkbox" });
  const proxima = new Date();
  proxima.setHours(proxima.getHours() + 1, 0, 0, 0); // la próxima hora en punto
  const aLas = el("input", { type: "datetime-local", value: valorLocal(proxima), "aria-label": "Fecha y hora del envío" });
  const campoProgramar = el("span", { class: "fila-campos" },
    el("label", { class: "interruptor" }, programar, "Programar para"), aLas);
  const alerta = el("div");
  const hecho = el("div");
  const boton = el("button", { class: "primario", type: "button" });

  const leerMinutos = () => {
    const m = Number(minutos.value);
    return Number.isInteger(m) && m >= 1 && m <= 1440 ? m : null;
  };
  const leerHora = () => {
    const d = new Date(aLas.value);
    return aLas.value && !Number.isNaN(d.getTime()) ? alMinuto(d) : null;
  };
  // Lo mismo que hace el motor: el plazo se cuenta desde el minuto programado.
  const plan = (inicio, m) => {
    const plazo = sumarMinutos(inicio, m);
    return { inicio, plazo, recolectar: sumarMinutos(plazo, RECOLECTAR_DESPUES), corregir: sumarMinutos(plazo, CORREGIR_DESPUES) };
  };

  // Solo textos y avisos: qué se manda al pedir el trabajo se decide en el clic.
  const actualizar = () => {
    const real = !prueba.checked;
    const m = leerMinutos();
    const hora = programar.checked ? leerHora() : null;
    campoProgramar.hidden = !real;
    aLas.disabled = !programar.checked;
    boton.classList.toggle("real", real);
    boton.disabled = !m || (real && programar.checked && !hora);
    boton.textContent = !real ? `Simular envío de ${tarea}`
      : hora ? `Programar el envío de ${tarea} para ${textoProgramado(hora)}` : `Enviar las preguntas de ${tarea}`;
    let aviso = "";
    if (real && hora && m) {
      const pl = plan(hora, m);
      aviso = `La pregunta sale ${textoProgramado(pl.inicio)}, con plazo hasta las ${horaCorta(pl.plazo)}. A las `
        + `${horaCorta(pl.recolectar)} se recolectan las respuestas y a las ${horaCorta(pl.corregir)} se corrigen, sin `
        + "mandar el feedback: queda para revisarlo en el paso 4. Una vez que sale no se puede deshacer.";
    } else if (real) {
      aviso = `Cada alumno recibe su pregunta por correo, con ${m || "?"} minutos para responder. No se puede deshacer.`;
    }
    alerta.replaceChildren(aviso ? el("div", { class: "nota-real" }, el("strong", {}, aviso)) : "");
  };
  [prueba, programar].forEach((x) => x.addEventListener("change", actualizar));
  [minutos, aLas].forEach((x) => x.addEventListener("input", actualizar));

  boton.addEventListener("click", async () => {
    const m = leerMinutos();
    const real = !prueba.checked;
    const hora = real && programar.checked ? leerHora() : null;
    if (!m) return;
    let pl = null;
    if (hora) {
      pl = plan(hora, m);
      if (pl.inicio.getTime() < Date.now() - 60_000) { alert("Esa hora ya pasó. Elige otra."); return; }
      if (!await confirmar(`Vas a programar las preguntas de ${tarea}: salen ${textoProgramado(pl.inicio)}, con ${m} minutos `
        + `para responder (hasta las ${horaCorta(pl.plazo)}). Después se recolectan y se corrigen solas, sin mandar el `
        + "feedback.\n\nSon correos reales. Hasta esa hora se puede cancelar en Últimos trabajos. ¿Confirmas?",
      boton.textContent, "real")) return;
    } else if (real && !await confirmar(`Vas a mandar las preguntas de ${tarea} a los alumnos, con ${m} minutos para `
      + "responder. Son correos reales.\n\n¿Confirmas?", boton.textContent, "real")) return;
    boton.disabled = true;
    hecho.replaceChildren();
    const pedidos = [];
    try {
      await editor.guardar();
      if (!pl) {
        const id = await pedirTrabajo(semestre, p.flujo, { tarea, prueba: !real, minutos: m });
        await seguir(id, destino);
      } else {
        // Si a algunos ya les llegó, el envío es para un grupo chico: recolectar
        // y corregir se quedan en él, para no tomar una respuesta tardía de otro
        // envío. Corregir sigue dejando fuera lo que llegue fuera de plazo.
        const solo = await correosDelEnvio(tarea);
        if (solo && !solo.length) throw new Error("no hay preguntas sin enviar con correo");
        const grupo = solo ? { solo } : {};
        pedidos.push(await pedirTrabajo(semestre, "tareas.enviar",
          { tarea, prueba: false, minutos: m, a_las: pl.inicio.toISOString() }));
        // Recolectar va a la cola de los reales (de a uno): así corregir no
        // corre a la vez y los dos no se pisan notas.csv.
        pedidos.push(await pedirTrabajo(semestre, "tareas.recolectar",
          { tarea, prueba: false, a_las: pl.recolectar.toISOString(), ...grupo }));
        pedidos.push(await pedirTrabajo(semestre, "tareas.corregir",
          { tarea, prueba: false, no_enviar: true, a_las: pl.corregir.toISOString(),
            ...(solo ? { solo, sin_tarde: true } : {}) }));
        hecho.replaceChildren(caja("exito", `Quedó programado. Las preguntas salen ${textoProgramado(pl.inicio)}, con `
          + `plazo hasta las ${horaCorta(pl.plazo)}; a las ${horaCorta(pl.recolectar)} se recolecta y a las `
          + `${horaCorta(pl.corregir)} se corrige, para revisar en el paso 4. Si alguien responde tarde, recolecta de `
          + "nuevo a mano."));
        await seguir(pedidos[0], destino);
      }
      historial.dibujar(semestre);
    } catch (e) {
      hecho.replaceChildren(caja("aviso", pedidos.length
        ? `Se programaron ${pedidos.length} de los 3 trabajos y el resto falló (${e.message}). Revisa Últimos trabajos.`
        : `No pude pedir el trabajo: ${e.message}`));
    } finally {
      actualizar();
    }
  });

  actualizar();
  return [
    editor.nodo,
    el("div", { class: "form-trabajo" },
      el("label", { class: "interruptor" }, prueba, "Solo simular"),
      el("label", {}, "Minutos para responder", minutos),
      campoProgramar,
      boton),
    alerta,
    hecho,
  ];
}

// ---------------------------------------------------------------- revisar antes de mandar

// Vuelve a leer las correcciones por revisar; la pestaña Corregir lo deja
// apuntando a su lista, y se llama al terminar cada trabajo.
let recargarRevision = () => {};

/** Los valores de la escala (tareas/prompts/escala.json), o null si el semestre no tiene. */
async function leerEscala() {
  try {
    const t = await leerTexto("tareas/prompts/escala.json");
    const valores = t.trim() ? JSON.parse(t).valores : null;
    return Array.isArray(valores) && valores.length ? valores.map(Number) : null;
  } catch {
    return null;
  }
}

/** Lo que respondió cada alumno en una tarea, por correo, desde el registro. */
async function respuestasDe(t) {
  const { columnas, filas } = leerCsv(await leerTexto("log_envios.csv"));
  const [iF, iI, iC, iE, iR] = ["Flujo", "Item", "Correo", "Evento", "Respuesta"].map((c) => columnas.indexOf(c));
  const respuestas = new Map();
  for (const f of filas) {
    if (enCsv(f[iF]) === "tarea" && enCsv(f[iI]).toUpperCase() === t && enCsv(f[iE]) === "respuesta" && enCsv(f[iR])) {
      respuestas.set(enCsv(f[iC]).toLowerCase(), f[iR]);
    }
  }
  return respuestas;
}

const textoNota = (v) => {
  const n = Number(String(v).replace(",", "."));
  if (String(v).trim() === "" || !Number.isFinite(n)) return String(v || "sin nota");
  return `${n > 0 ? "+" : ""}${n.toLocaleString("es-CL", { minimumFractionDigits: 1, maximumFractionDigits: 2 })}`;
};

/**
 * Las correcciones que quedaron sin mandar (corregir --no-enviar): la nota y el
 * comentario se pueden editar, y la justificación y la marca de IA del modelo se
 * leen aquí, porque al alumno no le llegan. "Mandar" pide tareas.feedback.
 */
function vistaRevision(destino) {
  const nodo = el("div", { class: "revision" });
  const t = tarea;
  const cargar = () => cargarRevision(nodo, destino, t)
    .catch((e) => nodo.replaceChildren(caja("aviso", `No pude leer las correcciones por revisar (${e.message}).`)));
  recargarRevision = () => { if (nodo.isConnected && tarea === t) cargar(); };
  if (buscar(rutaFeedbackDe(t))) cargar();
  return nodo;
}

async function cargarRevision(nodo, destino, t) {
  const ruta = rutaFeedbackDe(t);
  const leido = await leerConEtag(ruta);
  let etag = leido.etag;
  const csv = leerCsv(leido.texto);
  const col = (n) => csv.columnas.indexOf(n);
  const [iN, iG, iP, iQ, iC, iNota, iCom, iIA, iJ, iPend] = ["alumno_nombre", "grupo_archivo", "pregunta_tarea",
    "pregunta", "alumno_correo", "nota", "comentario", "senales_ia", "justificacion", "feedback_pendiente"].map(col);
  const pendientes = iPend < 0 ? [] : csv.filas.filter((f) => enCsv(f[iPend]) && enCsv(f[iC]));
  if (!pendientes.length) { nodo.replaceChildren(); return; }
  nodo.replaceChildren(el("p", { class: "cargando" }, "Cargando las correcciones por revisar…"));
  const [respuestas, escala] = await Promise.all([respuestasDe(t).catch(() => new Map()), leerEscala()]);
  if (tarea !== t || !nodo.isConnected) return;

  const editadas = new Set();
  const guardarBoton = el("button", { class: "secundario", type: "button", disabled: true }, "Guardar cambios");
  const mensaje = el("div");
  const guardar = async () => {
    if (!editadas.size) return;
    const n = editadas.size;
    etag = await guardarCsv(ruta, escribirCsv(csv), etag,
      `Editó ${n === 1 ? "una corrección" : `${n} correcciones`} de ${t} antes de mandarla${n === 1 ? "" : "s"}`) || etag;
    editadas.clear();
    guardarBoton.disabled = true;
  };
  guardarBoton.addEventListener("click", async () => {
    guardarBoton.disabled = true;
    try {
      await guardar();
      mensaje.replaceChildren(caja("exito", "Guardado. Al mandar sale lo que quedó escrito."));
    } catch (e) {
      mensaje.replaceChildren(caja("aviso", `No pude guardar: ${e.message}`));
      guardarBoton.disabled = false;
    }
  });

  const casillas = [];
  const fichas = pendientes.map((f) => {
    const correo = enCsv(f[iC]).toLowerCase();
    const casilla = el("input", { type: "checkbox", checked: true, value: correo });
    casillas.push(casilla);
    const actual = Number(enCsv(f[iNota]).replace(",", "."));
    // Una nota fuera de la escala (no debería pasar) se muestra igual, para que se vea y se cambie.
    const valores = escala && !escala.includes(actual) && enCsv(f[iNota]) ? [...escala, enCsv(f[iNota])] : escala;
    const nota = valores
      ? el("select", { "aria-label": `Nota de ${f[iN]}` }, valores.map((v) =>
        el("option", { value: String(v), selected: Number(v) === actual }, textoNota(v))))
      : el("input", { type: "text", value: f[iNota] || "", size: 5, "aria-label": `Nota de ${f[iN]}` });
    const comentario = el("textarea", { rows: 8, "aria-label": `Comentario para ${f[iN]}` }, f[iCom] || "");
    const insignia = el("span", { class: "estado" }, textoNota(f[iNota]));
    const cambio = () => {
      f[iNota] = nota.value;
      f[iCom] = comentario.value;
      insignia.textContent = textoNota(nota.value);
      editadas.add(f);
      guardarBoton.disabled = false;
      mensaje.replaceChildren();
    };
    nota.addEventListener("change", cambio);
    comentario.addEventListener("input", cambio);
    const ia = enCsv(f[iIA]);
    // Lo que anotó recolectar: otra dirección, adjuntos sin leer, varios correos.
    const aviso = col("aviso") >= 0 ? enCsv(f[col("aviso")]).trim() : "";
    return el("details", { class: "candidato" },
      el("summary", {},
        el("label", { class: "interruptor", onclick: (e) => e.stopPropagation() }, casilla, el("strong", {}, f[iN])),
        el("span", { class: "tenue" }, [f[iP], f[iG]].filter(Boolean).join(" · ")), " ", insignia,
        ia ? el("span", { class: "estado fallido", title: "El modelo vio señales de que la respuesta es de IA. "
          + "El alumno no lo ve." }, "señales de IA") : null,
        aviso ? el("span", { class: "estado", title: aviso }, "aviso") : null),
      el("div", { class: "contenido" },
        aviso ? caja("aviso", aviso) : null,
        el("p", {}, el("strong", {}, "Pregunta")), el("div", { class: "celda-lectura" }, f[iQ] || ""),
        el("p", {}, el("strong", {}, "Lo que respondió")),
        el("div", { class: "respuesta" }, respuestaLegible(respuestas.get(correo) || "(no la encontré en el registro)")),
        el("div", { class: "fila-campos" }, el("label", { class: "campo" }, "Nota", nota)),
        el("label", { class: "campo campo-ancho" }, "Comentario: es lo que recibe el alumno, con la nota", comentario),
        f[iJ] || ia ? el("p", { class: "nota-pie" }, el("strong", {}, "Solo para el equipo docente. "),
          ia ? "El modelo vio señales de que la respuesta es de IA. " : "", f[iJ] || "") : null));
  });

  const prueba = el("input", { type: "checkbox", checked: true });
  const mandar = el("button", { class: "primario", type: "button" });
  const actualizar = () => {
    const n = casillas.filter((c) => c.checked).length;
    mandar.classList.toggle("real", !prueba.checked);
    mandar.disabled = n === 0;
    mandar.textContent = n === 0 ? "Marca al menos una"
      : prueba.checked ? `Ver ${n === 1 ? "el correo de la elegida" : `los correos de las ${n} elegidas`}`
        : `Mandar ${n === 1 ? "la corrección elegida" : `las ${n} correcciones elegidas`}`;
  };
  casillas.forEach((c) => c.addEventListener("change", actualizar));
  prueba.addEventListener("change", actualizar);
  const todas = (v) => { casillas.forEach((c) => { c.checked = v; }); actualizar(); };

  mandar.addEventListener("click", async () => {
    const elegidos = casillas.filter((c) => c.checked).map((c) => c.value);
    const vacias = pendientes.filter((f) => elegidos.includes(enCsv(f[iC]).toLowerCase()) && !enCsv(f[iCom]));
    if (vacias.length) {
      alert(`El comentario quedó vacío para: ${vacias.map((f) => f[iN]).join(", ")}. Escríbelo o desmárcalas.`);
      return;
    }
    if (!prueba.checked && !await confirmar(`Vas a mandarle su corrección por correo a ${elegidos.length} `
      + `alumno${elegidos.length === 1 ? "" : "s"} de ${t}. Son correos reales.\n\n¿Confirmas?`, mandar.textContent,
    "real")) return;
    mandar.disabled = true;
    try {
      await guardar();
      const id = await pedirTrabajo(semestre, "tareas.feedback", { tarea: t, prueba: prueba.checked, solo: elegidos });
      destino.scrollIntoView({ behavior: "smooth", block: "start" });
      await seguir(id, destino);
      historial.dibujar(semestre);
    } catch (e) {
      mensaje.replaceChildren(caja("aviso", `No pude pedir el trabajo: ${e.message}`));
    } finally {
      actualizar();
    }
  });

  actualizar();
  nodo.replaceChildren(
    el("hr"),
    el("h4", {}, `Correcciones por revisar (${pendientes.length})`),
    el("p", { class: "nota-pie" }, "Las notas ya quedaron guardadas, pero el alumno no ha recibido nada. Si cambias "
      + "una nota, queda registrada como ajuste."),
    el("div", { class: "acciones" },
      el("button", { class: "enlace", type: "button", onclick: () => todas(true) }, "Todas"),
      el("button", { class: "enlace", type: "button", onclick: () => todas(false) }, "Ninguna")),
    ...fichas,
    el("div", { class: "acciones" }, guardarBoton),
    el("div", { class: "form-trabajo" }, el("label", { class: "interruptor" }, prueba, "Solo simular"), mandar),
    mensaje);
}

// ---------------------------------------------------------------- pantalla

function dibujar() {
  history.replaceState(null, "", `#${pestana.id}`);
  const resultado = el("div", { id: "resultado" });
  const vista = pestana.vista ? pestana.vista(pestana, resultado)
    : pestana.id === "generar" ? vistaGenerar(resultado) : vistaPaso(pestana, resultado);
  if (pestana.despues) vista.push(pestana.despues(resultado));
  else recargarRevision = () => {};
  // Primero qué tarea y en qué va; después los pasos.
  app.replaceChildren(
    el("div", { class: "cabeza-operacion" }, chipSemestre(semestre)),
    selectorTarea(), zonaEstado, zonaPestanas, zonaFalta, ...vista.filter(Boolean), resultado, el("hr"), historial.nodo);
  if (estadoTarea.tarea === tarea && estadoTarea.datos) pintarCabecera();
  else refrescarEstado();
  historial.dibujar(semestre);
}

async function iniciar() {
  try {
    const [semestres, parametros] = await Promise.all([api("/api/semestres"), api("/api/parametros")]);
    const activo = semestres.find((s) => s.activo);
    if (!activo) {
      app.replaceChildren(caja("aviso", "Elige un semestre en Configuración."));
      return;
    }
    semestre = activo.id;
    tareaPorDefecto = parametros.find((p) => p.clave === "TAREA_DEFAULT")?.valor || "T1";
    await actualizarArchivos();
    const conocidas = tareasConocidas(archivos);
    tarea = conocidas.includes(tareaPorDefecto) ? tareaPorDefecto : conocidas[0] || tareaPorDefecto;
    dibujar();
  } catch (e) {
    app.replaceChildren(caja("aviso", `No pude cargar la página: ${e.message}`));
  }
}

iniciar();
