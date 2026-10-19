// Tests Semanales: la misma página de Streamlit, operando en la nube.
//
// Cada botón pide un trabajo al sitio, que lo ejecuta el motor (Cloud Run) con
// los scripts de siempre. La salida se ve en vivo, y como el trabajo corre en
// la nube, cerrar la pestaña no lo detiene: queda en el historial de abajo.

import {
  api, barraPestanas, caja, chipSemestre, el, elegirCandidatos, enCuanto, fechaCorta, historialTrabajos, navegacion,
  pedirTrabajo, seguirTrabajo,
} from "./comun.js";
import { diaMes, leerCiclo } from "./ciclo.js";
import { resumenSemana } from "./preguntas.js";

document.getElementById("nav").replaceWith(navegacion());
const app = document.getElementById("app");

let semestre = null;
// La semana del formulario de la pestaña abierta.
let semanaElegida = 1;
// Los últimos trabajos del semestre (los del historial). Solo dicen si esta
// semana ya se simuló; dónde va la semana sale de notas.csv.
let trabajos = [];
// Lo que dice la nube de cada semana. undefined: cargando; false: no se pudo leer.
let estadoCurso;
// La pestaña abierta vuelve a mirar sus avisos cuando cambian los datos.
let alCambiarDatos = () => {};

// Las pestañas, en el orden del ciclo. `id` va en la URL y `flujo` es el
// trabajo que se pide: no cambian. Las marcadas `aparte` van fuera del ciclo.
const PESTANAS = [
  {
    id: "enviar", titulo: "1 · Enviar preguntas", flujo: "tests.enviar",
    prueba: "Solo simular",
    botonPrueba: "Simular envío",
    botonReal: "Enviar preguntas",
    alerta: "Cada alumno pendiente recibe la pregunta por correo. No se puede deshacer.",
    confirmar: (a) => `Vas a mandar la pregunta de la semana ${a.semana} a todos los alumnos que no la tienen. `
      + "Son correos reales.",
  },
  {
    id: "evaluar", titulo: "2 · Evaluar respuestas", flujo: "tests.evaluar",
    prueba: "Solo simular",
    botonPrueba: "Simular evaluación",
    botonReal: "Evaluar y mandar feedback",
    alerta: "Se llama al modelo, la nota queda guardada y cada alumno recibe su feedback por correo.",
    confirmar: (a) => `Vas a evaluar las respuestas de la semana ${a.semana} y mandarle el feedback a cada `
      + "alumno. Son correos reales y la nota queda guardada.",
  },
  {
    id: "resumen", titulo: "3 · Resumen semana", flujo: "tests.resumen",
    texto: "Resumen de la semana para el equipo docente, a partir de las evaluaciones.",
    info: "Llama al modelo. No manda correos.",
    boton: "Generar resumen",
    descarga: (a) => `tests_semanales/data/resumen_semana_${a.semana}.txt`,
  },
  {
    id: "tutoria", titulo: "Responder dudas", flujo: "tests.tutoria", aparte: true,
    texto: "Responde los correos de alumnos con dudas sobre su corrección. La nota no se modifica.",
    prueba: "Solo simular",
    botonPrueba: "Simular respuestas",
    botonReal: "Responder dudas",
    alerta: "Cada alumno recibe la respuesta por correo.",
    todasLasSemanas: true,
    confirmar: () => "Vas a responder por correo las dudas pendientes de los alumnos.",
  },
  {
    id: "experimento", titulo: "Probar criterio de evaluación", flujo: "tests.experimento", aparte: true,
    vista: (p, destino) => formularioExperimento(p, destino),
  },
];

let pestana = PESTANAS.find((p) => p.id === location.hash.slice(1)) || PESTANAS[0];

/** Abre una pestaña: en esa semana o, sin decir cuál, en la que le corresponde. */
function irA(id, semana) {
  pestana = PESTANAS.find((p) => p.id === id) || pestana;
  semanaElegida = semana || semanaPorDefecto(pestana.id);
  history.replaceState(null, "", `#${pestana.id}`);
  dibujar();
}

// ---------------------------------------------------------------- en qué va el curso
// La lectura vive en ciclo.js, que la comparte con Inicio.

const estadoDe = (n) => (estadoCurso ? estadoCurso.estadoDe(n) : { enviados: 0, primerEnvio: "", evaluadas: 0, sinNota: 0 });
const semanasEnviadas = () => (estadoCurso ? estadoCurso.enviadas() : []);
const entregaDe = (n) => (estadoCurso ? estadoCurso.entregaDe(n) : { texto: "", fecha: null });
const proximoPaso = () => (estadoCurso ? estadoCurso.proximoPaso() : null);

/** La semana en que conviene abrir cada pestaña. */
function semanaPorDefecto(id) {
  const enviadas = semanasEnviadas();
  const ultima = enviadas.at(-1) || 0;
  const prox = proximoPaso();
  if (id === "enviar") return ultima + 1;
  if (id === "evaluar") return prox?.paso === "evaluar" ? prox.semana : ultima || 1;
  if (id === "resumen") return enviadas.filter((n) => estadoDe(n).evaluadas).at(-1) || ultima || 1;
  return ultima || 1;
}

/** Un enlace que abre una pestaña en una semana. */
const irEn = (texto, paso, semana) => el("a", {
  href: `#${paso}`, onclick: (e) => { e.preventDefault(); irA(paso, semana); },
}, texto);

/** La frase de arriba: en qué va la semana abierta y qué viene, con fechas. */
function lineaEstado() {
  if (estadoCurso === undefined) return el("p", { class: "estado-curso" }, "Leyendo en qué va el curso…");
  if (!estadoCurso) {
    return el("p", { class: "estado-curso" },
      "No pude leer en qué va el curso (notas.csv). Las pestañas funcionan igual.");
  }
  const p = proximoPaso();
  if (!p?.paso) {
    return el("p", { class: "estado-curso" }, "Todas las semanas de preguntas.csv ya se enviaron y evaluaron.");
  }
  if (p.paso === "evaluar") {
    const s = estadoDe(p.semana);
    const envio = diaMes(s.primerEnvio);
    const evaluar = irEn("evaluar las respuestas", "evaluar", p.semana);
    return el("p", { class: "estado-curso" },
      el("strong", {}, `Semana ${p.semana}: `), `enviada a ${s.enviados}${envio ? ` el ${envio}` : ""}. `,
      !p.cuando ? ["No tiene fecha de entrega en preguntas.csv. Cuando corresponda, toca ", evaluar, "."]
        : p.ya ? [`La entrega cerró el ${fechaCorta(p.cuando)}; toca `, evaluar, "."]
          : [`La entrega cierra el ${fechaCorta(p.cuando)} (${enCuanto(p.cuando)}); después toca `, evaluar, "."]);
  }
  const ultima = semanasEnviadas().at(-1);
  return el("p", { class: "estado-curso" },
    ultima ? [el("strong", {}, `Semana ${ultima}: `), `evaluada, ${estadoDe(ultima).evaluadas} con nota. `] : "",
    "Lo próximo es ", irEn(`enviar la semana ${p.semana}`, "enviar", p.semana),
    p.cuando && !p.ya ? `, hacia el ${fechaCorta(p.cuando)} (${enCuanto(p.cuando)}).` : ".");
}

/** Las pestañas: los pasos de cada semana con en qué va cada uno, y las que se usan cuando se quiera. */
function pestanasDeTests() {
  const prox = estadoCurso ? proximoPaso() : null;
  const enviadas = semanasEnviadas();
  const ultima = enviadas.at(-1);
  const ultimaEvaluada = enviadas.filter((n) => estadoDe(n).evaluadas).at(-1);
  const detalle = { enviar: null, evaluar: null, resumen: "Opcional" };
  const hecho = { enviar: false, evaluar: false, resumen: false };
  if (estadoCurso) {
    if (prox?.paso === "enviar") {
      detalle.enviar = `Semana ${prox.semana} · ${prox.cuando && !prox.ya ? `hacia el ${fechaCorta(prox.cuando)}` : "ahora"}`;
    } else if (ultima) {
      const fecha = diaMes(estadoDe(ultima).primerEnvio);
      detalle.enviar = `Semana ${ultima} · a ${estadoDe(ultima).enviados}${fecha ? ` el ${fecha}` : ""}`;
      hecho.enviar = true;
    }
    if (prox?.paso === "evaluar") {
      detalle.evaluar = `Semana ${prox.semana} · ${prox.cuando && !prox.ya ? `desde ${fechaCorta(prox.cuando)}` : "ahora"}`;
    } else if (ultimaEvaluada) {
      detalle.evaluar = `Semana ${ultimaEvaluada} · ${estadoDe(ultimaEvaluada).evaluadas} con nota`;
      hecho.evaluar = true;
    }
    if (ultimaEvaluada) {
      hecho.resumen = estadoCurso.conResumen.has(ultimaEvaluada);
      detalle.resumen = hecho.resumen ? `Semana ${ultimaEvaluada}` : `Opcional · semana ${ultimaEvaluada}`;
    }
  }
  return barraPestanas({
    etiqueta: "Tests Semanales", actual: pestana.id, alElegir: (id) => irA(id), flujo: true,
    grupos: [
      { rotulo: "Cada semana", flechas: true, pestanas: [
        { id: "enviar", numero: 1, titulo: "Enviar preguntas", detalle: detalle.enviar, hecho: hecho.enviar,
          toca: prox?.paso === "enviar" },
        { id: "evaluar", numero: 2, titulo: "Evaluar respuestas", detalle: detalle.evaluar, hecho: hecho.evaluar,
          toca: prox?.paso === "evaluar" },
        { id: "resumen", numero: 3, titulo: "Resumen", detalle: detalle.resumen, hecho: hecho.resumen },
      ] },
      { rotulo: "Cuando quieras", pestanas: [
        { id: "tutoria", titulo: "Responder dudas" },
        { id: "experimento", titulo: "Probar criterio" },
      ] },
    ],
  });
}

const zonaEstado = el("div");
const zonaPestanas = el("div");
function pintarCabecera() {
  zonaEstado.replaceChildren(lineaEstado());
  zonaPestanas.replaceChildren(pestanasDeTests());
}

/** Vuelve a leer el historial y notas.csv (al entrar y cuando termina un trabajo). */
async function refrescarEstado() {
  const [lista, estado] = await Promise.allSettled([
    api(`/api/trabajos?semestre=${encodeURIComponent(semestre)}`), leerCiclo(semestre)]);
  if (lista.status === "fulfilled") trabajos = lista.value;
  estadoCurso = estado.status === "fulfilled" ? estado.value : false;
  pintarCabecera();
  alCambiarDatos();
}

/** Si esta semana tiene una evaluación simulada que terminó bien, entre los últimos trabajos. */
const simulada = (n) => trabajos.some((t) => t.flujo === "tests.evaluar" && t.prueba && t.estado === "terminado"
  && Number(t.argumentos?.semana) === n);

/** En qué está la semana elegida, dicho para el paso de esta pestaña. */
function estadoParaPestana(id, n) {
  if (!estadoCurso || !(n >= 1)) return "";
  const s = estadoDe(n);
  const { texto, fecha } = entregaDe(n);
  if (id === "enviar") {
    const cuando = diaMes(s.primerEnvio);
    return s.enviados ? `La semana ${n} ya se envió a ${s.enviados}${cuando ? ` el ${cuando}` : ""}. Si la envías de nuevo, `
      + "solo le llega a quien todavía no la tiene." : `La semana ${n} todavía no se envía.`;
  }
  if (id === "evaluar") {
    if (s.evaluadas) {
      return `La semana ${n} ya tiene ${s.evaluadas} respuestas con nota. Si la corres de nuevo, solo se evalúan `
        + "las respuestas nuevas.";
    }
    if (!s.enviados) return `La semana ${n} todavía no se envía: no hay respuestas que evaluar.`;
    if (fecha && fecha > new Date()) {
      return `La entrega de la semana ${n} cierra el ${fechaCorta(fecha)} (${enCuanto(fecha)}). Si evalúas antes, `
        + "las respuestas que lleguen después quedan para otra corrida.";
    }
    return `La entrega de la semana ${n} ya cerró${fecha ? ` (${fechaCorta(fecha)})` : texto ? ` (${texto})` : ""}.`;
  }
  if (id === "resumen") {
    return s.evaluadas ? `La semana ${n} tiene ${s.evaluadas} respuestas con nota.`
      : `La semana ${n} todavía no tiene notas: el resumen saldría vacío.`;
  }
  return "";
}

// ---------------------------------------------------------------- un trabajo en curso

/** Debajo de un resumen terminado, el enlace para bajar el archivo. */
function descarga(t) {
  // Después de revisar en modo prueba: elegir qué respuestas evaluar de verdad.
  if (t.flujo === "tests.evaluar" && t.prueba && t.estado === "terminado" && t.argumentos.semana) {
    // El semestre y la lista son los de esta revisión, no los del selector.
    const semana = t.argumentos.semana;
    return elegirCandidatos({
      semestre: t.semestre, ruta: `tests_semanales/cache/candidatos_${semana}_${t.id}.json`, verbo: "Evaluar",
      alProcesar: async (solo) => {
        const destino = document.getElementById("resultado");
        const id = await pedirTrabajo(t.semestre, "tests.evaluar", { semana, prueba: false, solo });
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
  return seguirTrabajo(id, destino, { extra: descarga, alTerminar: () => {
    historial.dibujar(semestre);
    refrescarEstado();
  } });
}

// ---------------------------------------------------------------- formulario

function formulario(p, destino) {
  const semana = el("input", { type: "number", min: "1", max: "52", value: String(semanaElegida) });
  const todas = p.todasLasSemanas ? el("input", { type: "checkbox", checked: true }) : null;
  const prueba = p.prueba ? el("input", { type: "checkbox", checked: true }) : null;
  const alerta = el("div");
  const boton = el("button", { class: "primario", type: "button" }, p.boton || p.botonPrueba);
  const campoSemana = el("label", {}, "Número de semana", semana);
  const estadoSemana = el("p", { class: "estado-semana" });

  // Solo textos y avisos: qué se manda al pedir el trabajo se decide en el clic.
  const actualizar = () => {
    if (todas) {
      semana.disabled = todas.checked;
      campoSemana.hidden = todas.checked;
    }
    const real = prueba && !prueba.checked;
    // Evaluar de verdad sin haber simulado esta semana: se puede, pero se avisa.
    const sinSimular = real && p.id === "evaluar" && !simulada(Number(semana.value));
    alerta.replaceChildren(real ? el("div", { class: "nota-real" }, el("strong", {}, p.alerta),
      sinSimular ? el("p", { class: "precondicion" },
        "No simulaste esta semana: no verás antes qué respuestas se evaluarán.") : null) : "");
    boton.classList.toggle("real", Boolean(real));
    if (prueba) boton.textContent = real ? p.botonReal : p.botonPrueba;
    estadoSemana.textContent = todas?.checked ? "" : estadoParaPestana(p.id, Number(semana.value));
  };
  todas?.addEventListener("change", actualizar);
  prueba?.addEventListener("change", actualizar);
  alCambiarDatos = actualizar;

  // Al enviar, las preguntas de esa semana a la vista: qué se va a mandar.
  const resumen = p.id === "enviar" ? resumenSemana(semestre) : null;
  resumen?.mostrar(semanaElegida, { enviada: estadoDe(semanaElegida).enviados > 0 });
  semana.addEventListener("input", () => {
    const n = Number(semana.value);
    if (n >= 1) {
      semanaElegida = n;
      resumen?.mostrar(n, { enviada: estadoDe(n).enviados > 0 });
    }
    actualizar();
  });

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
    p.texto ? el("p", {}, p.texto) : null,
    p.info ? caja("info", p.info) : null,
    p.nota ? el("p", { class: "nota-pie" }, p.nota) : null,
    el("div", { class: "form-trabajo" },
      todas ? el("label", { class: "interruptor" }, todas, "Todas las semanas") : null,
      campoSemana,
      prueba ? el("label", { class: "interruptor" }, prueba, p.prueba) : null,
      boton),
    estadoSemana,
    alerta,
    resumen?.nodo,
  ];
}

// ---------------------------------------------------------------- probar un criterio de evaluación

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
  const semana = el("input", { type: "number", min: "1", max: "52", value: String(semanaElegida), disabled: true });
  const campoSemana = el("label", {}, "Semana", semana);
  const semilla = el("input", { type: "number", min: "0", max: "99999", value: "19",
    title: "La misma semilla elige la misma muestra. Deja fija la semilla para comparar dos prompts "
      + "sobre las mismas respuestas." });
  const soloMuestra = el("input", { type: "checkbox", checked: true });
  const aviso = el("div");
  const boton = el("button", { class: "primario", type: "button" });
  alCambiarDatos = () => {};

  const actualizar = () => {
    semana.disabled = todas.checked;
    campoSemana.hidden = todas.checked;
    boton.textContent = soloMuestra.checked ? "Ver la muestra" : `Probar el criterio (hasta ${n.value} llamadas)`;
    aviso.replaceChildren(soloMuestra.checked ? ""
      : caja("aviso", `Hasta ${n.value} llamadas a la API. Las notas no cambian.`));
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
    el("p", {}, "Reevalúa respuestas ya corregidas con un prompt distinto y compara notas y originalidad. "
      + "No manda correos ni cambia el prompt del semestre."),
    el("label", { class: "campo" }, "Prompt candidato", area),
    el("div", { class: "form-trabajo" },
      el("label", {}, "Cuántas respuestas", n),
      el("label", { class: "interruptor" }, todas, "Todas las semanas"),
      campoSemana,
      el("label", {}, "Semilla", semilla),
      el("label", { class: "interruptor" }, soloMuestra, "Solo ver la muestra"),
      boton),
    aviso,
  ];
}

// ---------------------------------------------------------------- historial

const historial = historialTrabajos({
  incluye: (t) => t.flujo.startsWith("tests."),
  columna: ["Semana", (a) => a.semana ?? "todas"],
  alElegir: (t) => {
    const destino = document.getElementById("resultado");
    seguir(t.id, destino);
    destino.scrollIntoView({ behavior: "smooth", block: "start" });
  },
});

// ---------------------------------------------------------------- pantalla

function dibujar() {
  const resultado = el("div", { id: "resultado" });
  pintarCabecera();
  app.replaceChildren(
    el("div", { class: "cabeza-operacion" }, chipSemestre(semestre)),
    zonaEstado, zonaPestanas,
    ...(pestana.vista || formulario)(pestana, resultado).filter(Boolean), resultado, el("hr"), historial.nodo);
  historial.dibujar(semestre);
}

async function iniciar() {
  try {
    const semestres = await api("/api/semestres");
    const activo = semestres.find((s) => s.activo);
    if (!activo) {
      app.replaceChildren(caja("aviso",
        "No hay un semestre activo. Elígelo en Configuración."));
      return;
    }
    semestre = activo.id;
    await refrescarEstado();
    semanaElegida = semanaPorDefecto(pestana.id);
    dibujar();
  } catch (e) {
    app.replaceChildren(caja("aviso", `No pude cargar la página: ${e.message}`));
  }
}

iniciar();
