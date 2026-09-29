// Tareas: la misma página de Streamlit, operando en la nube.
//
// Los cuatro pasos (generar, enviar, recolectar, corregir) son trabajos del
// motor, igual que en Tests Semanales. El chequeo de las entregas también: lee
// los HTML en el motor y deja el resultado en tareas/cache/, que esta página
// dibuja. No llama al modelo.

import {
  api, caja, el, elegirCandidatos, historialTrabajos, navegacion, pedirTrabajo, seguirTrabajo,
  tareasConocidas,
} from "./comun.js";
import { escribirCsv, leerCsv } from "./csv.js";

document.getElementById("nav").replaceWith(navegacion());
const app = document.getElementById("app");

let semestre = null;
let archivos = [];
let tarea = null;
let tareaPorDefecto = "T1";

const PESTANAS = [
  { id: "generar", titulo: "1 · Generar preguntas", flujo: "tareas.generar" },
  {
    id: "enviar", titulo: "2 · Enviar preguntas", flujo: "tareas.enviar",
    texto: "Envía las preguntas personalizadas a los alumnos con correo en el CSV.",
    prueba: "Modo prueba — no envía emails",
    alerta: "Modo prueba desactivado — se enviarán emails reales.",
    confirmar: () => `Vas a mandar las preguntas de ${tarea} a los alumnos. Son correos reales.`,
  },
  {
    id: "recolectar", titulo: "3 · Recolectar respuestas", flujo: "tareas.recolectar",
    texto: "Busca las respuestas a los emails enviados y las guarda en CSV.",
    info: "No envía emails — solo lee el inbox y actualiza el CSV.",
  },
  {
    id: "corregir", titulo: "4 · Corregir", flujo: "tareas.corregir",
    texto: "Evalúa las respuestas con GPT, asigna notas y envía feedback por correo.",
    prueba: "Modo prueba — no llama a GPT ni envía emails",
    alerta: "Modo prueba desactivado — se consumirán tokens y se enviarán emails.",
    noEnviar: "Solo corregir, no enviar emails",
    nota: "Conviene correrlo primero en modo prueba: muestra las respuestas pendientes y deja elegir a "
      + "quién corregir. Las demás siguen pendientes.",
    confirmar: (a) => (a.no_enviar
      ? `Vas a corregir ${tarea} con GPT (gasta tokens) y guardar las notas, sin mandar correos.`
      : `Vas a corregir ${tarea} con GPT y mandarle el feedback por correo a cada alumno. Son correos reales.`),
  },
  { id: "segunda", titulo: "Segunda oportunidad", flujo: "tareas.segunda", vista: (p, d) => vistaSegunda(d) },
];

let pestana = PESTANAS.find((p) => p.id === location.hash.slice(1)) || PESTANAS[0];

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

// ---------------------------------------------------------------- historial

const historial = historialTrabajos({
  // Los chequeos se piden solos al abrir la pestaña 1: listarlos taparía los
  // trabajos que sí importan.
  incluye: (t) => t.flujo.startsWith("tareas.") && t.flujo !== "tareas.chequeo",
  columna: ["Tarea", (a) => a.tarea ?? ""],
  alElegir: (t) => seguir(t.id, document.getElementById("resultado")),
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
  return seguirTrabajo(id, destino, { extra: elegir, alTerminar: () => historial.dibujar(semestre) });
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
      contenido.push(caja("aviso", "Este grupo no declaró quién hizo qué. Cada integrante trae una pregunta "
        + "repartida al azar (con semilla fija, así que no cambia sola entre corridas). Cámbiala acá si "
        + "sabes cuál le corresponde."));
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
          el("span", { class: "falta-correo" }, "Sin correo — elígelo en Datos → Feedback Tareas"),
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
      // Sin pisar una asignación que otra persona guardó mientras tanto.
      ...(previo ? { "if-match": previo.etag } : { "if-none-match": "*" }),
    },
  });
  mensaje.replaceChildren(caja("exito", `Guardado en asignacion_${tarea}.csv. Generar va a usar esto.`));
}

/** Qué material del curso va a ver el modelo al generar (modulos/tareas/contexto.py). */
function lineaContexto(c) {
  if (!c) return null; // chequeo guardado antes de que existiera este dato
  const enlace = el("a", { href: "/datos#datos/contexto" }, "Datos y Configuración → Contexto del curso");
  if (!c.activo) return el("p", { class: "nota-pie" }, "Contexto del curso: apagado.");
  if (!c.archivos.length) {
    return caja("aviso", el("span", {}, "Sin contexto del curso: las preguntas se van a generar sin ver el material "
      + "de las clases. Súbelo en ", enlace, "."));
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
        el("p", { class: "nota-pie" }, "Revisa la lista antes de sacar conclusiones: acá también cae el equipo "
          + "docente, si está en el roster."),
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
  destino.replaceChildren(caja("info", "Revisando las entregas en el motor… (no llama al modelo)"));
  try {
    const id = await pedirTrabajo(semestre, "tareas.chequeo", { tarea: tareaPedida });
    const salida = el("div", { hidden: true });
    destino.append(salida);
    await seguirTrabajo(id, salida, {
      alTerminar: async (t) => {
        if (tarea !== tareaPedida) return; // cambiaron de tarea mientras corría
        if (t.estado !== "terminado") { salida.hidden = false; return; }
        await actualizarArchivos();
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
  const partes = [el("p", {}, "Procesa los HTMLs de U-Cursos, genera una pregunta de comprensión por alumno "
    + "y resuelve correos contra el CSV.")];
  const casillas = htmls.map((n) => el("input", { type: "checkbox", checked: true, value: n }));
  const boton = el("button", { class: "primario", type: "button", disabled: !htmls.length }, "Ejecutar");
  const actualizar = () => { boton.disabled = !casillas.some((c) => c.checked); };
  for (const c of casillas) c.addEventListener("change", actualizar);

  if (!htmls.length) {
    partes.push(caja("aviso", `No hay archivos HTML para ${tarea} en entregas/${tarea}/. Súbelos desde la página `
      + "Datos y Configuración → Datos del curso → Entregas (Tareas), eligiendo esta misma tarea."));
  } else {
    const todos = (v) => { for (const c of casillas) c.checked = v; actualizar(); };
    partes.push(el("details", {},
      el("summary", {}, `HTMLs a procesar (${htmls.length} disponibles para ${tarea})`),
      el("div", { class: "contenido" },
        el("div", { class: "acciones" },
          el("button", { class: "enlace", type: "button", onclick: () => todos(true) }, "Todos"),
          el("button", { class: "enlace", type: "button", onclick: () => todos(false) }, "Ninguno")),
        el("div", { class: "lista-casillas" }, htmls.map((n, i) =>
          el("label", { class: "interruptor" }, casillas[i], n))))));

    const chequeo = el("div");
    partes.push(el("hr"), el("h4", {}, "Estado de las entregas"),
      el("p", { class: "nota-pie" }, "Esto se calcula leyendo los archivos: no llama al modelo ni gasta API. "
        + "Arregla lo que aparezca marcado antes de generar."), chequeo);
    if (chequeoAlDia()) {
      mostrarChequeo(chequeo).catch(() => revisar(chequeo));
    } else {
      revisar(chequeo);
    }
  }

  partes.push(
    caja("info", "Los nombres sin match en el CSV quedarán con correo vacío de forma preliminar. Es necesario "
      + "corregirlos manualmente desde Datos → Feedback Tareas."),
    el("div", { class: "form-trabajo" }, boton));

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
  const preparar = el("button", { class: "primario", type: "button" }, "Preparar preguntas nuevas");
  preparar.addEventListener("click", () => pedir({ paso: "preparar" }, preparar));

  const prueba = el("input", { type: "checkbox", checked: true });
  const alerta = el("div");
  const enviar = el("button", { class: "primario", type: "button" }, "Enviar");
  const actualizar = () => {
    alerta.replaceChildren(prueba.checked ? "" : caja("aviso", "Modo prueba desactivado — se enviarán emails reales."));
    enviar.classList.toggle("peligro", !prueba.checked);
    enviar.textContent = prueba.checked ? "Ver los borradores" : "Enviar (envío real)";
  };
  prueba.addEventListener("change", actualizar);
  enviar.addEventListener("click", () => {
    if (!prueba.checked && !confirm(`Vas a mandar la pregunta nueva de ${tarea} a quienes no respondieron la `
      + "primera. Son correos reales. Quien ya la recibió no la recibe de nuevo.\n\n¿Confirmas?")) return;
    pedir({ paso: "enviar", prueba: prueba.checked }, enviar);
  });
  actualizar();

  return [
    el("p", {}, "Una pregunta nueva, sobre la misma parte de la tarea, para quienes recibieron la primera y no "
      + "respondieron. Después, recolectar y corregir funcionan como siempre, contra la pregunta nueva."),
    el("h4", {}, "1 · Preparar"),
    caja("info", "Llama al modelo, una vez por alumno; no manda correos. Si ya estaba preparada, solo completa "
      + "las preguntas que falten."),
    el("div", { class: "form-trabajo" }, preparar),
    vista,
    el("h4", {}, "2 · Enviar"),
    el("div", { class: "form-trabajo" },
      el("label", { class: "interruptor" }, prueba, "Modo prueba — solo arma los borradores, no envía"), enviar),
    alerta,
  ];
}

function vistaPaso(p, destino) {
  const prueba = p.prueba ? el("input", { type: "checkbox", checked: true }) : null;
  const noEnviar = p.noEnviar ? el("input", { type: "checkbox" }) : null;
  const alerta = el("div");
  const boton = el("button", { class: "primario", type: "button" }, "Ejecutar");

  const actualizar = () => {
    const real = prueba && !prueba.checked;
    alerta.replaceChildren(real ? caja("aviso", p.alerta) : "");
    const envia = real && !(noEnviar && noEnviar.checked);
    boton.classList.toggle("peligro", Boolean(real));
    boton.textContent = envia ? "Ejecutar (envío real)" : "Ejecutar";
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
    el("p", {}, p.texto),
    p.info ? caja("info", p.info) : null,
    p.nota ? el("p", { class: "nota-pie" }, p.nota) : null,
    el("div", { class: "form-trabajo" },
      prueba ? el("label", { class: "interruptor" }, prueba, p.prueba) : null,
      noEnviar ? el("label", { class: "interruptor" }, noEnviar, p.noEnviar) : null,
      boton),
    alerta,
  ];
}

// ---------------------------------------------------------------- pantalla

function dibujar() {
  history.replaceState(null, "", `#${pestana.id}`);
  const pestanas = el("div", { class: "pestanas", role: "tablist" }, PESTANAS.map((p) => el("button", {
    class: "pestana", role: "tab", type: "button", "aria-selected": String(p === pestana),
    onclick: () => { pestana = p; dibujar(); },
  }, p.titulo)));
  const resultado = el("div", { id: "resultado" });
  const vista = pestana.vista ? pestana.vista(pestana, resultado)
    : pestana.id === "generar" ? vistaGenerar(resultado) : vistaPaso(pestana, resultado);
  app.replaceChildren(
    el("p", { class: "subtitulo" }, `Semestre activo: ${semestre}`),
    pestanas, selectorTarea(), ...vista.filter(Boolean), resultado, el("hr"), historial.nodo);
  historial.dibujar(semestre);
}

async function iniciar() {
  try {
    const [semestres, parametros] = await Promise.all([api("/api/semestres"), api("/api/parametros")]);
    const activo = semestres.find((s) => s.activo);
    if (!activo) {
      app.replaceChildren(caja("aviso", "Elige un semestre en Datos y Configuración para operar las tareas."));
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
