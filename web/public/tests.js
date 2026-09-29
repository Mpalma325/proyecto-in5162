// Tests Semanales: la misma página de Streamlit, operando en la nube.
//
// Cada botón pide un trabajo al sitio, que lo ejecuta el motor (Cloud Run) con
// los scripts de siempre. La salida se ve en vivo, y como el trabajo corre en
// la nube, cerrar la pestaña no lo detiene: queda en el historial de abajo.

import {
  api, caja, el, elegirCandidatos, historialTrabajos, navegacion, pedirTrabajo, seguirTrabajo,
} from "./comun.js";

document.getElementById("nav").replaceWith(navegacion());
const app = document.getElementById("app");

let semestre = null;

// Las pestañas, en el mismo orden y con los mismos textos que en Streamlit.
const PESTANAS = [
  {
    id: "enviar", titulo: "1 · Enviar preguntas", flujo: "tests.enviar",
    texto: "Envía la pregunta de la semana a todos los alumnos pendientes.",
    prueba: "Modo prueba — no envía emails",
    alerta: "Modo prueba desactivado — se enviarán emails reales.",
    confirmar: (a) => `Vas a mandar la pregunta de la semana ${a.semana} a todos los alumnos que no la tienen. `
      + "Son correos reales.",
  },
  {
    id: "evaluar", titulo: "2 · Evaluar respuestas", flujo: "tests.evaluar",
    texto: "Lee el inbox, evalúa respuestas con GPT y envía feedback a cada alumno.",
    prueba: "Modo prueba — no envía ni guarda cambios",
    alerta: "Modo prueba desactivado — se evaluarán y enviarán emails reales.",
    nota: "Conviene correrlo primero en modo prueba: muestra las respuestas que encontró y deja elegir "
      + "cuáles evaluar. Las que no se elijan quedan sin leer en el buzón.",
    confirmar: (a) => `Vas a evaluar las respuestas de la semana ${a.semana} y mandarle el feedback a cada `
      + "alumno. Son correos reales y la nota queda guardada.",
  },
  {
    id: "resumen", titulo: "3 · Resumen semana", flujo: "tests.resumen",
    texto: "Genera el resumen semanal para el profesor a partir de las evaluaciones del CSV.",
    info: "No envía emails ni modifica datos — solo genera un archivo de texto. Sí llama al modelo.",
    descarga: (a) => `tests_semanales/data/resumen_semana_${a.semana}.txt`,
  },
  {
    id: "tutoria", titulo: "Tutoría", flujo: "tests.tutoria",
    texto: "Responde las dudas que los alumnos mandan sobre su corrección: por qué esa nota, "
      + "qué se esperaba, o algún concepto que les quedó dando vueltas.",
    info: "La nota no se modifica. Acá el agente explica y enseña; corregir de nuevo sería otra cosa.",
    nota: "Va aparte del ciclo del curso: córrelo cuando quieras. Si nunca lo corres, no pasa nada: "
      + "los correos quedan sin leer esperando.",
    prueba: "Modo prueba — no envía emails",
    alerta: "Modo prueba desactivado — se enviarán respuestas reales.",
    todasLasSemanas: true,
    confirmar: () => "Vas a responder por correo las dudas pendientes de los alumnos.",
  },
  {
    id: "experimento", titulo: "Probar un prompt", flujo: "tests.experimento",
    vista: (p, destino) => formularioExperimento(p, destino),
  },
];

let pestana = PESTANAS.find((p) => p.id === location.hash.slice(1)) || PESTANAS[0];

// ---------------------------------------------------------------- un trabajo en curso

/** Debajo de un resumen terminado, el enlace para bajar el archivo. */
function descarga(t) {
  // Después de revisar en modo prueba: elegir qué respuestas evaluar de verdad.
  if (t.flujo === "tests.evaluar" && t.prueba && t.estado === "terminado" && t.argumentos.semana) {
    const semana = t.argumentos.semana;
    return elegirCandidatos({
      semestre, ruta: `tests_semanales/cache/candidatos_${semana}.json`, verbo: "Evaluar",
      alProcesar: async (solo) => {
        const destino = document.getElementById("resultado");
        const id = await pedirTrabajo(semestre, "tests.evaluar", { semana, prueba: false, solo });
        await seguir(id, destino);
      },
    });
  }
  if (t.flujo === "tests.experimento" && t.estado === "terminado") {
    // El nombre lleva la hora de la corrida; se toma de la línea "(guardados ...)" del motor.
    const ruta = (t.salida.match(/tests_semanales\/data\/experimento_[\w-]+\.csv/) || [])[0];
    return ruta ? el("a", { class: "descarga",
      href: `/api/archivo/${encodeURIComponent(semestre)}/${ruta}?descargar` }, `Descargar ${ruta.split("/").pop()}`) : null;
  }
  const p = PESTANAS.find((x) => x.flujo === t.flujo);
  if (t.estado !== "terminado" || !p?.descarga || !t.argumentos.semana) return null;
  const ruta = p.descarga(t.argumentos);
  return el("a", {
    class: "descarga", href: `/api/archivo/${encodeURIComponent(semestre)}/${ruta}?descargar`,
  }, `Descargar ${ruta.split("/").pop()}`);
}

function seguir(id, destino) {
  return seguirTrabajo(id, destino, { extra: descarga, alTerminar: () => historial.dibujar(semestre) });
}

// ---------------------------------------------------------------- formulario

function formulario(p, destino) {
  const semana = el("input", { type: "number", min: "1", max: "52", value: "1" });
  const todas = p.todasLasSemanas ? el("input", { type: "checkbox", checked: true }) : null;
  const prueba = p.prueba ? el("input", { type: "checkbox", checked: true }) : null;
  const alerta = el("div");
  const boton = el("button", { class: "primario", type: "button" }, "Ejecutar");

  const actualizar = () => {
    if (todas) semana.disabled = todas.checked;
    const real = prueba && !prueba.checked;
    alerta.replaceChildren(real ? caja("aviso", p.alerta) : "");
    boton.classList.toggle("peligro", Boolean(real));
    boton.textContent = real ? "Ejecutar (envío real)" : "Ejecutar";
  };
  todas?.addEventListener("change", actualizar);
  prueba?.addEventListener("change", actualizar);

  boton.addEventListener("click", async () => {
    const argumentos = { prueba: prueba ? prueba.checked : true };
    if (!(todas && todas.checked)) argumentos.semana = Number(semana.value);
    if (p.confirmar && prueba && !prueba.checked) {
      // Desde el celular es fácil tocar sin querer, y el costo del error es
      // mandarle correos a todo el curso. El modo prueba no pide confirmación.
      if (!confirm(`${p.confirmar(argumentos)}\n\n¿Confirmas?`)) return;
    }
    boton.disabled = true;
    try {
      const id = await pedirTrabajo(semestre, p.flujo, argumentos);
      history.replaceState(null, "", `#${p.id}`);
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
      todas ? el("label", { class: "interruptor" }, todas, "Todas las semanas") : null,
      el("label", {}, "Número de semana", semana),
      prueba ? el("label", { class: "interruptor" }, prueba, p.prueba) : null,
      boton),
    alerta,
  ];
}

// ---------------------------------------------------------------- probar un prompt

function formularioExperimento(p, destino) {
  const area = el("textarea", { class: "prompt", spellcheck: "false" }, "Cargando el prompt vigente…");
  area.disabled = true;
  fetch(`/api/archivo/${encodeURIComponent(semestre)}/tests_semanales/prompts/evaluar_respuesta.md`,
    { cache: "no-store" })
    .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`${r.status}`))))
    .then((texto) => { area.value = texto; area.disabled = false; })
    .catch(() => { area.value = ""; area.disabled = false; });

  const n = el("input", { type: "number", min: "1", max: "300", step: "5", value: "20" });
  const todas = el("input", { type: "checkbox", checked: true });
  const semana = el("input", { type: "number", min: "1", max: "52", value: "1", disabled: true });
  const semilla = el("input", { type: "number", min: "0", max: "99999", value: "19",
    title: "La misma semilla elige la misma muestra. Deja fija la semilla para comparar dos prompts "
      + "sobre las mismas respuestas." });
  const soloMuestra = el("input", { type: "checkbox", checked: true });
  const aviso = el("div");
  const boton = el("button", { class: "primario", type: "button" }, "Ejecutar");

  const actualizar = () => {
    semana.disabled = todas.checked;
    aviso.replaceChildren(soloMuestra.checked
      ? caja("info", "Con esto activado el prompt candidato no se prueba: solo se lista qué respuestas se "
        + "reevaluarían, con la nota que ya tienen. Apágalo para que el modelo corrija de verdad y haya algo "
        + "que comparar.")
      : caja("aviso", `Se harán hasta ${n.value} llamadas reales a la API. Las notas de los alumnos no cambian.`));
  };
  for (const x of [todas, soloMuestra, n]) x.addEventListener("input", actualizar);

  boton.addEventListener("click", async () => {
    const argumentos = { prompt: area.value, n: Number(n.value), semilla: Number(semilla.value),
      prueba: soloMuestra.checked };
    if (!todas.checked) argumentos.semana = Number(semana.value);
    if (!argumentos.prompt.trim()) { destino.replaceChildren(caja("aviso", "El prompt está vacío.")); return; }
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
    el("p", {}, "Reevalúa respuestas que el curso ya corrigió con un prompt distinto y las compara una a una "
      + "contra la nota y la originalidad que se les puso en su momento. Sirve para ver si un cambio en el prompt "
      + "mueve la distribución de originalidad antes de aplicarlo al curso."),
    caja("info", "No manda correos, no cambia ninguna nota y no escribe en el log. El resultado queda en un CSV "
      + "aparte. Lo único que gasta es API: una llamada por respuesta."),
    el("p", { class: "nota-pie" }, "Empieza con el prompt vigente. Edítalo acá y prueba: el archivo del semestre "
      + "no se toca, así que la evaluación real sigue usando el de siempre hasta que decidas cambiarlo."),
    el("label", { class: "campo" }, "Prompt candidato", area),
    el("div", { class: "form-trabajo" },
      el("label", {}, "Cuántas respuestas", n),
      el("label", { class: "interruptor" }, todas, "Todas las semanas"),
      el("label", {}, "Semana", semana),
      el("label", {}, "Semilla", semilla),
      el("label", { class: "interruptor" }, soloMuestra, "Solo mostrar la muestra — no llama al modelo"),
      boton),
    aviso,
  ];
}

// ---------------------------------------------------------------- historial

const historial = historialTrabajos({
  incluye: (t) => t.flujo.startsWith("tests."),
  columna: ["Semana", (a) => a.semana ?? "todas"],
  alElegir: (t) => seguir(t.id, document.getElementById("resultado")),
});

// ---------------------------------------------------------------- pantalla

function dibujar() {
  const pestanas = el("div", { class: "pestanas", role: "tablist" }, PESTANAS.map((p) => el("button", {
    class: "pestana", role: "tab", type: "button", "aria-selected": String(p === pestana),
    onclick: () => { pestana = p; history.replaceState(null, "", `#${p.id}`); dibujar(); },
  }, p.titulo)));
  const resultado = el("div", { id: "resultado" });
  app.replaceChildren(
    el("p", { class: "subtitulo" }, `Semestre activo: ${semestre}`),
    pestanas, ...(pestana.vista || formulario)(pestana, resultado).filter(Boolean), resultado, el("hr"), historial.nodo);
  historial.dibujar(semestre);
}

async function iniciar() {
  try {
    const semestres = await api("/api/semestres");
    const activo = semestres.find((s) => s.activo);
    if (!activo) {
      app.replaceChildren(caja("aviso",
        "No hay un semestre activo. Elígelo en Datos y Configuración para operar los tests."));
      return;
    }
    semestre = activo.id;
    dibujar();
  } catch (e) {
    app.replaceChildren(caja("aviso", `No pude cargar la página: ${e.message}`));
  }
}

iniciar();
