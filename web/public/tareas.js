// Tareas: la misma página de Streamlit, operando en la nube.
//
// Los cuatro pasos (generar, enviar, recolectar, corregir) son trabajos del
// motor, igual que en Tests Semanales. El chequeo de las entregas también: lee
// los HTML en el motor y deja el resultado en tareas/cache/, que esta página
// dibuja. No llama al modelo.

import {
  api, barraPestanas, caja, chipSemestre, el, elegirCandidatos, historialTrabajos, navegacion, pedirTrabajo,
  seguirTrabajo, tareasConocidas, conDetalle,
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
    prueba: "Solo simular",
    botonPrueba: () => `Simular envío de ${tarea}`,
    botonReal: () => `Enviar las preguntas de ${tarea}`,
    alerta: () => "Cada alumno recibe su pregunta por correo. No se puede deshacer.",
    confirmar: () => `Vas a mandar las preguntas de ${tarea} a los alumnos. Son correos reales.`,
  },
  {
    id: "recolectar", titulo: "3 · Recolectar respuestas", flujo: "tareas.recolectar",
    info: "Solo lee el buzón. Se puede repetir.",
    boton: () => `Recolectar respuestas de ${tarea}`,
  },
  {
    id: "corregir", titulo: "4 · Corregir", flujo: "tareas.corregir",
    prueba: "Solo simular",
    noEnviar: "Guardar las notas sin mandar el feedback",
    botonPrueba: () => `Simular corrección de ${tarea}`,
    botonReal: (envia) => (envia ? `Corregir ${tarea} y mandar feedback` : `Corregir ${tarea} sin mandar correos`),
    alerta: (envia) => (envia
      ? "Se llama al modelo (gasta API), las notas quedan guardadas y cada alumno recibe su feedback por correo."
      : "Se llama al modelo (gasta API) y las notas quedan guardadas. No sale ningún correo."),
    confirmar: (a) => (a.no_enviar
      ? `Vas a corregir ${tarea} con GPT (gasta tokens) y guardar las notas, sin mandar correos.`
      : `Vas a corregir ${tarea} con GPT y mandarle el feedback por correo a cada alumno. Son correos reales.`),
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
const buscar = (ruta) => archivos.find((a) => a.ruta === ruta);

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

async function leerTexto(ruta) {
  const r = await fetch(urlArchivo(ruta), { cache: "no-store" });
  if (r.status === 404) return "";
  if (!r.ok) throw new Error(String(r.status));
  return r.text();
}

async function leerEstadoTarea(t) {
  const rutaFeedback = `tareas/data/salidas/feedback_${t}.csv`;
  const [notas, feedback] = await Promise.all([leerTexto("notas.csv"),
    buscar(rutaFeedback) ? leerTexto(rutaFeedback) : ""]);
  const datos = { generadas: 0, enviados: 0, primerEnvio: "", respondieron: 0, corregidas: 0 };
  if (feedback.trim()) {
    const { columnas, filas } = leerCsv(feedback);
    const ip = columnas.indexOf("pregunta");
    datos.generadas = filas.filter((f) => (f[ip] || "").trim()).length;
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
      : d.corregidas ? plural(d.corregidas, "corregida", "corregidas") : null;
    hecho.generar = d.generadas > 0;
    hecho.enviar = d.enviados > 0;
    hecho.recolectar = d.enviados > 0 && d.respondieron >= d.enviados;
    hecho.corregir = d.corregidas > 0 && porCorregir === 0;
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
}

// ---------------------------------------------------------------- historial

const historial = historialTrabajos({
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
  // El semestre y la lista son los de esta revisión, no los del selector.
  return elegirCandidatos({
    semestre: t.semestre, ruta: `tareas/cache/candidatos_${tareaRevisada}_${t.id}.json`, verbo: "Corregir",
    alProcesar: async (solo) => {
      const id = await pedirTrabajo(t.semestre, "tareas.corregir", { tarea: tareaRevisada, prueba: false, solo });
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
  } });
}

// ---------------------------------------------------------------- selector de tarea

function selectorTarea() {
  const opciones = tareasConocidas(archivos);
  const texto = el("input", { type: "text", size: 6, pattern: "T\\d{1,2}" });
  const cambiar = (t) => {
    const valor = t.trim().toUpperCase();
    if (!/^T\d{1,2}$/.test(valor) || valor === tarea) return;
    tarea = valor;
    dibujar();
  };
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

function grupoChequeo(g, selects) {
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
        i.correo ? el("code", {}, i.correo) : el("div", {},
          el("span", { class: "falta-correo" }, "Sin correo en Configuración › Tareas › Alumnos"),
          i.candidatos.length
            ? i.candidatos.map(([n, c, sim]) => el("div", { class: "nota-pie" }, `¿${n}? ${c} (parecido ${sim})`))
            : el("div", { class: "nota-pie" }, "Ningún candidato razonable en el roster.")),
        pregunta || el("span"));
    })));
  }
  return el("details", { open: g.bloqueo.length > 0 || g.sin_roles },
    el("summary", {}, `${icono} ${g.archivo} — ${resumen}`),
    el("div", { class: "contenido" }, contenido));
}

async function guardarAsignacion(selects, mensaje) {
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
  mensaje.replaceChildren(caja("exito", `Guardado en asignacion_${tarea}.csv. Generar va a usar esto.`));
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

function dibujarChequeo(informe, destino, cuando) {
  const grupos = informe.grupos;
  if (!grupos.length) {
    destino.replaceChildren(caja("aviso", "No hay entregas que revisar."));
    return;
  }
  const activos = grupos.filter((g) => !g.bloqueo.length);
  const aGenerar = activos.reduce((n, g) => n + g.integrantes.filter((i) => i.correo).length, 0);
  const sinCorreo = activos.reduce((n, g) => n + g.integrantes.filter((i) => !i.correo).length, 0);
  const selects = [];
  const mensaje = el("div");
  const partes = [
    el("p", { class: "nota-pie" }, `Revisado el ${cuando} · `,
      el("button", { class: "enlace", type: "button", onclick: () => revisar(destino) }, "Volver a revisar")),
    lineaContexto(informe.contexto),
    el("div", { class: "kpis", style: "grid-template-columns: repeat(3, 1fr)" },
      kpi("Preguntas que se generarían", aGenerar), kpi("Sin correo, a resolver", sinCorreo),
      kpi("Grupos que se saltarían", grupos.length - activos.length)),
    ...grupos.map((g) => grupoChequeo(g, selects)),
  ];
  if (grupos.some((g) => Object.keys(g.asignacion).length)) {
    const boton = el("button", { class: "descarga", type: "button" }, "Guardar asignación");
    boton.addEventListener("click", async () => {
      boton.disabled = true;
      try {
        await guardarAsignacion(selects, mensaje);
        await actualizarArchivos();
      } catch (e) {
        mensaje.replaceChildren(caja("aviso", `No pude guardar: ${e.message}`));
      } finally {
        boton.disabled = false;
      }
    });
    partes.push(el("div", { class: "acciones" }, boton), mensaje);
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
  const informe = JSON.parse(await (await fetch(urlArchivo(rutaChequeo()), { cache: "no-store" })).text());
  const cuando = new Date(info.subido).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" });
  dibujarChequeo(informe, destino, cuando);
}

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
        await mostrarChequeo(destino);
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
  const partes = [];
  const casillas = htmls.map((n) => el("input", { type: "checkbox", checked: true, value: n }));
  const boton = el("button", { class: "primario", type: "button", disabled: !htmls.length },
    `Generar preguntas de ${tarea}`);
  const actualizar = () => { boton.disabled = !casillas.some((c) => c.checked); };
  for (const c of casillas) c.addEventListener("change", actualizar);

  if (!htmls.length) {
    partes.push(caja("aviso", el("span", {}, `No hay entregas de ${tarea}. Se suben en `,
      el("a", { href: "/datos#datos/entregas" }, "Configuración › Tareas › Entregas"), ".")));
  } else {
    const todos = (v) => { for (const c of casillas) c.checked = v; actualizar(); };
    partes.push(el("details", {},
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
    el("p", { class: "nota-pie" }, "Los nombres que no calcen con Configuración › Tareas › Alumnos quedan sin correo."),
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
            el("td", {}, f[col("enviado")] ? new Date(f[col("enviado")]).toLocaleString("es-CL",
              { dateStyle: "short", timeStyle: "short" }) : "—")))))),
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
  enviar.addEventListener("click", () => {
    if (!prueba.checked && !confirm(`Vas a mandar la pregunta nueva de ${tarea} a quienes no respondieron la `
      + "primera. Son correos reales. Quien ya la recibió no la recibe de nuevo.\n\n¿Confirmas?")) return;
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
  const noEnviar = p.noEnviar ? el("input", { type: "checkbox" }) : null;
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
    if (p.confirmar && prueba && !prueba.checked && !confirm(`${p.confirmar(argumentos)}\n\n¿Confirmas?`)) return;
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

// ---------------------------------------------------------------- pantalla

function dibujar() {
  history.replaceState(null, "", `#${pestana.id}`);
  const resultado = el("div", { id: "resultado" });
  const vista = pestana.vista ? pestana.vista(pestana, resultado)
    : pestana.id === "generar" ? vistaGenerar(resultado) : vistaPaso(pestana, resultado);
  // Primero qué tarea y en qué va; después los pasos.
  app.replaceChildren(
    el("div", { class: "cabeza-operacion" }, chipSemestre(semestre)),
    selectorTarea(), zonaEstado, zonaPestanas, ...vista.filter(Boolean), resultado, el("hr"), historial.nodo);
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
