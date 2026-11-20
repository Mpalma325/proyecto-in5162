// Tests Semanales: la misma página de Streamlit, operando en la nube.
//
// Cada botón pide un trabajo al sitio, que lo ejecuta el motor (Cloud Run) con
// los scripts de siempre. La salida se ve en vivo, y como el trabajo corre en
// la nube, cerrar la pestaña no lo detiene: queda en el historial de abajo.
//
// En un semestre con preguntas.csv del formato nuevo (columna Instancia) se
// elige la instancia por su nombre («Control 2») y el trabajo lleva
// `instancia`; en uno antiguo, el número de semana y `semana`, como siempre.
//
// Qué pasa después de corregir lo dice cada instancia, con su interruptor
// «Revisar las correcciones antes de enviarlas» (columna Revision de
// preguntas.csv; vacía, configuracion.json): apagado, el feedback sale en el
// mismo trabajo; encendido, las correcciones esperan en la pestaña Revisar
// (revision.js). El interruptor está en Evaluar y en Revisar, y en
// Configuración › Preguntas. Sin columna ni archivo rige lo de antes.

import {
  api, barraPestanas, caja, chipSemestre, confirmar, el, elegirCandidatos, enCuanto, fechaCorta, historialTrabajos,
  idDe, navegacion, nombreInstancia, pedirTrabajo, seguirTrabajo,
} from "./comun.js";
import { diaMes, leerCiclo } from "./ciclo.js";
import { describirModo, REVISAR } from "./configuracion.js";
import { interruptorDeInstancia, leerSemana, resumenSemana, semanasDe } from "./preguntas.js";
import { pestanaRevisar } from "./revision.js";

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
// El modo de revisión de una instancia (ciclo.js, modoDe): `auto`, `revisar`,
// o null mientras no se lea.
const modoDe = (n) => (estadoCurso ? estadoCurso.modoDe(n) : null);
// Sin saber el modo, los textos avisan que el correo sale: si se equivocan, que sea hacia el lado seguro.
const enRevision = (n) => modoDe(n) === REVISAR;
// Si alguna instancia del semestre se revisa antes de enviar (para «Nada pendiente» en Revisar).
const algunaEnRevision = () => Boolean(estadoCurso?.preguntas)
  && (legado() ? enRevision(1) : semanasDe(estadoCurso.preguntas).some((s) => enRevision(s.numero)));
// Un texto de PESTANAS puede depender del modo de la instancia elegida: entonces es una función de su id.
const segunModo = (v, ...a) => (typeof v === "function" ? v(...a) : v);

// Formato antiguo (columna Semana) mientras no se sepa otra cosa.
const legado = () => !estadoCurso || estadoCurso.legado !== false;
const nombre = (n) => (legado() ? `Semana ${n}` : estadoCurso.nombre(n));
const mencion = (n) => (legado() ? `la semana ${n}` : estadoCurso.nombre(n));
const Mencion = (n) => { const t = mencion(n); return t[0].toUpperCase() + t.slice(1); };
// En las pestañas: «semana 4» o «Control 2».
const corto = (n) => (legado() ? `semana ${n}` : nombre(n));
/** La instancia del formato nuevo (con estado, envío y cierre), o null. */
const instanciaDe = (n) => (!legado() && estadoCurso.preguntas ? leerSemana(estadoCurso.preguntas, n) : null);
const enBorrador = (n) => instanciaDe(n)?.estado === "borrador";

// Las pestañas, en el orden del ciclo. `id` va en la URL y `flujo` es el
// trabajo que se pide: no cambian. Las marcadas `aparte` van fuera del ciclo.
const PESTANAS = [
  {
    id: "enviar", titulo: "1 · Enviar preguntas", flujo: "tests.enviar",
    prueba: "Solo simular",
    botonPrueba: "Simular envío",
    botonReal: "Enviar preguntas",
    alerta: "Cada alumno pendiente recibe la pregunta por correo. No se puede deshacer.",
    confirmar: (a) => `Vas a mandar la pregunta de ${mencion(idDe(a))} a todos los alumnos que no la tienen. `
      + "Son correos reales.",
  },
  {
    id: "evaluar", titulo: "2 · Evaluar respuestas", flujo: "tests.evaluar",
    prueba: "Solo simular",
    botonPrueba: "Simular evaluación",
    botonReal: (n) => (enRevision(n) ? "Corregir y dejar para revisión" : "Evaluar y mandar feedback"),
    alerta: (n) => (enRevision(n)
      ? "Se llama al modelo y cada corrección queda esperando en Revisar. El alumno no recibe nada todavía, salvo "
        + "el correo de duplicado si respondió dos veces."
      : "Se llama al modelo, la nota queda guardada y cada alumno recibe su feedback por correo."),
    confirmar: (a) => (enRevision(idDe(a))
      ? `Vas a corregir las respuestas de ${mencion(idDe(a))}. Las correcciones quedan esperando tu revisión en `
        + "Tests › Revisar: el alumno no recibe nada todavía, salvo el correo de duplicado a quien respondió dos veces."
      : `Vas a evaluar las respuestas de ${mencion(idDe(a))} y mandarle el feedback a cada `
        + "alumno. Son correos reales y la nota queda guardada."),
  },
  // Revisar no pide un trabajo al abrirla: muestra las correcciones (revision.js).
  { id: "revisar", titulo: "3 · Revisar", revisar: true },
  {
    id: "resumen", titulo: "4 · Resumen semana", flujo: "tests.resumen",
    texto: () => `Resumen de ${legado() ? "la semana" : "la instancia"} para el equipo docente, a partir de las `
      + "evaluaciones.",
    info: "Llama al modelo. No manda correos.",
    boton: "Generar resumen",
    descarga: (a) => `tests_semanales/data/resumen_semana_${idDe(a)}.txt`,
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
];

// Probar criterio vivía acá; ahora está en Configuración › La IA.
if (location.hash === "#experimento") location.replace("/datos#datos/probar");

/** «#revisar/12» → { id: "revisar", n: 12 }. El id de la instancia solo va en la URL de Revisar. */
const leerHash = () => {
  const [id, n] = location.hash.slice(1).split("/");
  return { id, n: Number(n) >= 1 ? Number(n) : null };
};
let pestana = PESTANAS.find((p) => p.id === leerHash().id) || PESTANAS[0];
// La instancia abierta en Revisar; null: la primera con algo pendiente.
let revisarId = leerHash().n;

const hashDe = (id) => (id === "revisar" && revisarId ? `#revisar/${revisarId}` : `#${id}`);

/** Abre una pestaña: en esa semana o, sin decir cuál, en la que le corresponde. */
function irA(id, semana) {
  pestana = PESTANAS.find((p) => p.id === id) || pestana;
  semanaElegida = semana || semanaPorDefecto(pestana.id);
  if (pestana.id === "revisar" && semana) revisarId = semana;
  history.replaceState(null, "", hashDe(pestana.id));
  dibujar();
}

// Cambiar solo el # (un marcador, la barra de direcciones) también cambia de
// pestaña. irA usa replaceState, que no dispara hashchange: no hay bucle.
window.addEventListener("hashchange", () => {
  if (location.hash === "#experimento") { location.replace("/datos#datos/probar"); return; }
  const { id, n } = leerHash();
  if (!semestre || !PESTANAS.some((p) => p.id === id)) return;
  if (id !== pestana.id) irA(id, id === "revisar" ? n : undefined);
  else if (id === "revisar" && n && n !== revisarId) irA(id, n);
});

// ---------------------------------------------------------------- en qué va el curso
// La lectura vive en ciclo.js, que la comparte con Inicio.

const estadoDe = (n) => (estadoCurso ? estadoCurso.estadoDe(n)
  : { enviados: 0, primerEnvio: "", evaluadas: 0, sinNota: 0, porRevisar: 0, descartadas: 0, corregidas: 0 });
/** Cuántas correcciones esperan revisión en todo el semestre. */
const totalPorRevisar = () => (estadoCurso?.porRevisar ? estadoCurso.porRevisar().reduce((s, [, k]) => s + k, 0) : 0);
const semanasEnviadas = () => (estadoCurso ? estadoCurso.enviadas() : []);
const entregaDe = (n) => (estadoCurso ? estadoCurso.entregaDe(n) : { texto: "", fecha: null });
const proximoPaso = () => (estadoCurso ? estadoCurso.proximoPaso() : null);

/** La semana en que conviene abrir cada pestaña. */
function semanaPorDefecto(id) {
  const enviadas = semanasEnviadas();
  const ultima = enviadas.at(-1) || 0;
  const prox = proximoPaso();
  if (!legado()) {
    // Sin semanas: la que toca según sus fechas, o la primera que hay.
    const primera = semanasDe(estadoCurso.preguntas)[0]?.numero || 1;
    if (id === "enviar") return prox?.paso === "enviar" ? prox.semana : primera;
    if (id === "evaluar") return prox?.paso === "evaluar" ? prox.semana : ultima || primera;
    if (id === "resumen") return enviadas.filter((n) => estadoDe(n).evaluadas).at(-1) || ultima || primera;
    return ultima || primera;
  }
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
    return el("p", { class: "estado-curso" }, legado() ? "Todas las semanas de preguntas.csv ya se enviaron y evaluaron."
      : "Todas las instancias de preguntas.csv ya se enviaron y evaluaron.");
  }
  if (p.paso === "evaluar") {
    const s = estadoDe(p.semana);
    const envio = diaMes(s.primerEnvio);
    const evaluar = irEn("evaluar las respuestas", "evaluar", p.semana);
    return el("p", { class: "estado-curso" },
      el("strong", {}, `${nombre(p.semana)}: `), `enviada a ${s.enviados}${envio ? ` el ${envio}` : ""}. `,
      !p.cuando ? ["No tiene fecha de entrega en preguntas.csv. Cuando corresponda, toca ", evaluar, "."]
        : p.ya ? [`La entrega cerró el ${fechaCorta(p.cuando)}; toca `, evaluar, "."]
          : [`La entrega cierra el ${fechaCorta(p.cuando)} (${enCuanto(p.cuando)}); después toca `, evaluar, "."]);
  }
  const ultima = semanasEnviadas().at(-1);
  const cuando = p.borrador ? ", que está en borrador: confírmala en Configuración › Preguntas."
    : p.cuando && !p.ya ? `, ${legado() ? "hacia" : "programado para"} el ${fechaCorta(p.cuando)} (${enCuanto(p.cuando)}).` : ".";
  const porRevisar = ultima ? estadoDe(ultima).porRevisar : 0;
  return el("p", { class: "estado-curso" },
    ultima ? [el("strong", {}, `${nombre(ultima)}: `), `evaluada, ${estadoDe(ultima).evaluadas} con nota`,
      // «Sin enviar» y no «por revisar»: la cuenta sale de notas.csv, que no
      // distingue las que el docente ya aprobó (eso lo dice la pestaña Revisar).
      porRevisar ? [" y ", irEn(`${porRevisar} sin enviar`, "revisar", ultima)] : "", ". "] : "",
    "Lo próximo es ", irEn(`enviar ${mencion(p.semana)}`, "enviar", p.semana), cuando);
}

/** Las pestañas: los pasos de cada semana con en qué va cada uno, y las que se usan cuando se quiera. */
function pestanasDeTests() {
  const prox = estadoCurso ? proximoPaso() : null;
  const enviadas = semanasEnviadas();
  const ultima = enviadas.at(-1);
  const ultimaEvaluada = enviadas.filter((n) => estadoDe(n).evaluadas).at(-1);
  const ultimaCorregida = enviadas.filter((n) => estadoDe(n).corregidas).at(-1);
  const porRevisar = totalPorRevisar();
  const detalle = { enviar: null, evaluar: null, resumen: "Opcional",
    revisar: porRevisar ? `${porRevisar} sin enviar` : algunaEnRevision() ? "Nada pendiente" : null };
  const hecho = { enviar: false, evaluar: false, resumen: false };
  if (estadoCurso) {
    if (prox?.paso === "enviar") {
      detalle.enviar = `${nombre(prox.semana)} · ${prox.borrador ? "en borrador"
        : prox.cuando && !prox.ya ? `hacia el ${fechaCorta(prox.cuando)}` : "ahora"}`;
    } else if (ultima) {
      const fecha = diaMes(estadoDe(ultima).primerEnvio);
      detalle.enviar = `${nombre(ultima)} · a ${estadoDe(ultima).enviados}${fecha ? ` el ${fecha}` : ""}`;
      hecho.enviar = true;
    }
    if (prox?.paso === "evaluar") {
      detalle.evaluar = `${nombre(prox.semana)} · ${prox.cuando && !prox.ya ? `desde ${fechaCorta(prox.cuando)}` : "ahora"}`;
    } else if (ultimaCorregida) {
      // En revisión, «corregida» todavía no es nota: la nota existe cuando sale el feedback.
      const s = estadoDe(ultimaCorregida);
      detalle.evaluar = `${nombre(ultimaCorregida)} · ${s.porRevisar ? `${s.corregidas} corregidas`
        : `${s.evaluadas} con nota`}`;
      hecho.evaluar = true;
    }
    if (ultimaEvaluada) {
      hecho.resumen = estadoCurso.conResumen.has(ultimaEvaluada);
      detalle.resumen = hecho.resumen ? nombre(ultimaEvaluada) : `Opcional · ${corto(ultimaEvaluada)}`;
    }
  }
  return barraPestanas({
    etiqueta: "Tests", actual: pestana.id, alElegir: (id) => irA(id), flujo: true,
    grupos: [
      { rotulo: legado() ? "Cada semana" : "Cada instancia", flechas: true, pestanas: [
        { id: "enviar", numero: 1, titulo: "Enviar preguntas", detalle: detalle.enviar, hecho: hecho.enviar,
          toca: prox?.paso === "enviar" },
        { id: "evaluar", numero: 2, titulo: "Evaluar respuestas", detalle: detalle.evaluar, hecho: hecho.evaluar,
          toca: prox?.paso === "evaluar" },
        { id: "revisar", numero: 3, titulo: "Revisar", detalle: detalle.revisar, toca: porRevisar > 0 },
        { id: "resumen", numero: 4, titulo: "Resumen", detalle: detalle.resumen, hecho: hecho.resumen },
      ] },
      { rotulo: "Cuando quieras", pestanas: [
        { id: "tutoria", titulo: "Responder dudas" },
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
  // El ciclo trae también el modo de cada instancia (preguntas.csv y configuracion.json).
  estadoCurso = estado.status === "fulfilled" ? estado.value : false;
  columnaHistorial[0] = legado() ? "Semana" : "Instancia";
  pintarCabecera();
  alCambiarDatos();
}

/** Si esta semana tiene una evaluación simulada que terminó bien, entre los últimos trabajos. */
const simulada = (n) => trabajos.some((t) => t.flujo === "tests.evaluar" && t.prueba && t.estado === "terminado"
  && Number(idDe(t.argumentos)) === n);

/** En qué está la semana elegida, dicho para el paso de esta pestaña. */
function estadoParaPestana(id, n) {
  if (!estadoCurso || !(n >= 1)) return "";
  const s = estadoDe(n);
  const { texto, fecha } = entregaDe(n);
  const info = instanciaDe(n);
  if (!legado() && !info) return `No hay una instancia con ese id en preguntas.csv.`;
  if (id === "enviar") {
    const cuando = diaMes(s.primerEnvio);
    if (s.enviados) {
      return `${Mencion(n)} ya se envió a ${s.enviados}${cuando ? ` el ${cuando}` : ""}. Si la envías de nuevo, `
        + "solo le llega a quien todavía no la tiene.";
    }
    if (info?.estado === "borrador") {
      return `${Mencion(n)} está en borrador: puedes simular el envío, pero para mandarla de verdad hay que `
        + "confirmarla en Configuración › Preguntas.";
    }
    if (info?.envio && new Date(info.envio) > new Date()) {
      return `${Mencion(n)} está confirmada y sale sola el ${fechaCorta(new Date(info.envio))}. Enviarla ahora `
        + "adelanta el envío; a la hora programada ya no le llega a nadie más.";
    }
    return `${Mencion(n)} todavía no se envía.`;
  }
  if (id === "evaluar") {
    if (s.corregidas) {
      const partes = [s.evaluadas ? `${s.evaluadas} con nota` : "", s.porRevisar ? `${s.porRevisar} sin enviar` : "",
        s.descartadas ? `${s.descartadas} descartadas` : ""].filter(Boolean);
      return `${Mencion(n)} ya tiene ${s.corregidas} respuestas corregidas (${partes.join(", ")}). Si la corres de `
        + "nuevo, solo se corrigen las respuestas nuevas.";
    }
    if (!s.enviados) return `${Mencion(n)} todavía no se envía: no hay respuestas que evaluar.`;
    if (fecha && fecha > new Date()) {
      return `La entrega de ${mencion(n)} cierra el ${fechaCorta(fecha)} (${enCuanto(fecha)}). Si evalúas antes, `
        + "las respuestas que lleguen después quedan para otra corrida."
        + (info?.estado !== "confirmada" ? "" : enRevision(n)
          ? " Al cierre se corrige sola y las correcciones quedan esperando en Revisar."
          : " Al cierre se evalúa sola.");
    }
    if (!fecha && !texto) return `${Mencion(n)} no tiene fecha de entrega en preguntas.csv: evalúa cuando corresponda.`;
    return `La entrega de ${mencion(n)} ya cerró${fecha ? ` (${fechaCorta(fecha)})` : ` (${texto})`}.`;
  }
  if (id === "resumen") {
    return s.evaluadas ? `${Mencion(n)} tiene ${s.evaluadas} respuestas con nota.`
      : `${Mencion(n)} todavía no tiene notas: el resumen saldría vacío.`;
  }
  return "";
}

// ---------------------------------------------------------------- un trabajo en curso

/** Debajo de un resumen terminado, el enlace para bajar el archivo. */
function descarga(t) {
  // Después de revisar en modo prueba: elegir qué respuestas evaluar de verdad.
  if (t.flujo === "tests.evaluar" && t.prueba && t.estado === "terminado" && idDe(t.argumentos)) {
    // El semestre y la lista son los de esta revisión, no los del selector.
    const semana = idDe(t.argumentos);
    const clave = t.argumentos.instancia ? "instancia" : "semana";
    // Si esa instancia se revisa, no sale feedback: los textos lo dicen y se puede corregir a mano.
    const revisar = enRevision(Number(semana));
    return elegirCandidatos({
      semestre: t.semestre, ruta: `tests_semanales/cache/candidatos_${semana}_${t.id}.json`,
      verbo: revisar ? "Corregir con IA" : "Evaluar", mandaFeedback: !revisar, aMano: revisar,
      textoConfirmar: revisar ? (nombres) => `Vas a corregir con IA a: ${nombres}.\n\nNo sale feedback todavía: cada `
        + "corrección espera tu revisión en Tests › Revisar. Las demás quedan como están. ¿Confirmas?" : undefined,
      alProcesar: async (solo, extra = {}) => {
        const destino = document.getElementById("resultado");
        const id = await pedirTrabajo(t.semestre, "tests.evaluar", { [clave]: semana, prueba: false, solo, ...extra });
        await seguir(id, destino);
      },
    });
  }
  const p = PESTANAS.find((x) => x.flujo === t.flujo);
  if (t.estado !== "terminado" || !p?.descarga || !idDe(t.argumentos)) return null;
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

/** En el formato nuevo, la lista de instancias por su nombre; el valor es el id. */
function selectorInstancia() {
  const lista = semanasDe(estadoCurso.preguntas);
  if (!lista.some((s) => s.numero === semanaElegida) && lista.length) semanaElegida = lista[0].numero;
  return el("select", {}, lista.map((s) => el("option", { value: String(s.numero), selected: s.numero === semanaElegida },
    `${s.nombre}${s.tema.trim() ? ` · ${s.tema.trim()}` : ""}${s.estado === "borrador" ? " (borrador)" : ""}`)));
}

function formulario(p, destino) {
  const semana = legado() ? el("input", { type: "number", min: "1", max: "52", value: String(semanaElegida) })
    : selectorInstancia();
  const todas = p.todasLasSemanas ? el("input", { type: "checkbox", checked: true }) : null;
  const prueba = p.prueba ? el("input", { type: "checkbox", checked: true }) : null;
  const alerta = el("div");
  const boton = el("button", { class: "primario", type: "button" }, p.boton || p.botonPrueba);
  const campoSemana = el("label", {}, legado() ? "Número de semana" : "Instancia", semana);
  const estadoSemana = el("p", { class: "estado-semana" });
  // En Evaluar, el interruptor de revisión de la instancia elegida.
  const zonaModo = p.id === "evaluar" ? el("div", { class: "zona-modo" }) : null;
  const pintarModo = () => zonaModo?.replaceChildren(...bloqueModo(Number(semana.value)));

  // Solo textos y avisos: qué se manda al pedir el trabajo se decide en el clic.
  const actualizar = () => {
    if (todas) {
      semana.disabled = todas.checked;
      campoSemana.hidden = todas.checked;
    }
    const real = prueba && !prueba.checked;
    // Evaluar de verdad sin haber simulado esta semana: se puede, pero se avisa.
    const sinSimular = real && p.id === "evaluar" && !simulada(Number(semana.value));
    // Un borrador no sale de verdad (el motor también se niega): primero se confirma.
    const bloqueado = real && !todas?.checked && enBorrador(Number(semana.value));
    alerta.replaceChildren(bloqueado ? caja("aviso", `${Mencion(Number(semana.value))} está en borrador. Confírmala en `
      + "Configuración › Preguntas antes de mandarla de verdad; en borrador solo se puede simular.")
      : real ? el("div", { class: "nota-real" }, el("strong", {}, segunModo(p.alerta, Number(semana.value))),
        sinSimular ? el("p", { class: "precondicion" },
          `No simulaste ${legado() ? "esta semana" : "esta instancia"}: no verás antes qué respuestas se evaluarán.`)
          : null) : "");
    // Solo lo toca el bloqueo: mientras se pide un trabajo, el clic lo deshabilita aparte.
    if (bloqueado || boton.classList.contains("bloqueado")) boton.disabled = Boolean(bloqueado);
    boton.classList.toggle("bloqueado", Boolean(bloqueado));
    boton.classList.toggle("real", Boolean(real));
    if (prueba) boton.textContent = real ? segunModo(p.botonReal, Number(semana.value)) : p.botonPrueba;
    estadoSemana.textContent = todas?.checked ? "" : estadoParaPestana(p.id, Number(semana.value));
  };
  todas?.addEventListener("change", actualizar);
  prueba?.addEventListener("change", actualizar);
  alCambiarDatos = actualizar;

  // Al enviar, las preguntas de esa semana a la vista: qué se va a mandar.
  const resumen = p.id === "enviar" ? resumenSemana(semestre) : null;
  resumen?.mostrar(semanaElegida, { enviada: estadoDe(semanaElegida).enviados > 0 });
  semana.addEventListener(legado() ? "input" : "change", () => {
    const n = Number(semana.value);
    if (n >= 1) {
      semanaElegida = n;
      resumen?.mostrar(n, { enviada: estadoDe(n).enviados > 0 });
    }
    pintarModo();
    actualizar();
  });

  boton.addEventListener("click", async () => {
    const argumentos = { prueba: prueba ? prueba.checked : true };
    if (!(todas && todas.checked)) {
      const n = Number(semana.value);
      if (!legado() && !(n >= 1)) {
        destino.replaceChildren(caja("aviso", "Todavía no hay instancias: créalas en Configuración › Preguntas."));
        return;
      }
      if (prueba && !prueba.checked && enBorrador(n)) return;
      argumentos[legado() ? "semana" : "instancia"] = n;
    }
    if (p.confirmar && prueba && !prueba.checked) {
      // Desde el celular es fácil tocar sin querer, y el costo del error es
      // mandarle correos a todo el curso. El modo prueba no pide confirmación.
      if (!await confirmar(`${p.confirmar(argumentos)}\n\n¿Confirmas?`, segunModo(p.botonReal, idDe(argumentos)),
        "real")) return;
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

  pintarModo();
  actualizar();
  return [
    p.texto ? el("p", {}, segunModo(p.texto)) : null,
    p.info ? caja("info", p.info) : null,
    p.nota ? el("p", { class: "nota-pie" }, p.nota) : null,
    el("div", { class: "form-trabajo" },
      todas ? el("label", { class: "interruptor" }, todas, legado() ? "Todas las semanas" : "Todas") : null,
      campoSemana,
      prueba ? el("label", { class: "interruptor" }, prueba, p.prueba) : null,
      boton),
    zonaModo,
    estadoSemana,
    alerta,
    resumen?.nodo,
  ];
}

// ---------------------------------------------------------------- historial

// El título cambia a «Instancia» en un semestre del formato nuevo (refrescarEstado).
const columnaHistorial = ["Semana", (a) => (a.instancia ? nombreInstancia(a.instancia) : a.semana ?? "todas")];
const historial = historialTrabajos({
  // Las pruebas de criterio tienen su propio historial, en Configuración.
  prefijo: "tests.",
  incluye: (t) => t.flujo.startsWith("tests.") && t.flujo !== "tests.experimento",
  columna: columnaHistorial,
  alElegir: (t) => {
    const destino = document.getElementById("resultado");
    seguir(t.id, destino);
    destino.scrollIntoView({ behavior: "smooth", block: "start" });
  },
});

// ---------------------------------------------------------------- pantalla

/**
 * Qué pasa después de corregir la instancia `n`: su interruptor «Revisar las
 * correcciones antes de enviarlas», que se guarda apenas se aprieta. En el
 * formato antiguo (semanas) no hay interruptor: se dice lo que rige.
 */
function bloqueModo(n) {
  if (!estadoCurso) return [];
  if (legado()) {
    // Sin configuracion.json, lo de antes; si no se pudo leer, el trabajo revisa (configuracion.py).
    const conf = estadoCurso.configuracion;
    return [el("p", { class: "nota-pie" }, conf && !conf.existe
      ? "Este semestre usa la configuración de antes: cada corrección se le manda al alumno apenas queda lista."
      : `Después de corregir, ${describirModo(modoDe(n) || REVISAR)}.`)];
  }
  if (!instanciaDe(n)) return [];
  const mensaje = el("div");
  return [interruptorDeInstancia({
    semestre, numero: n, nombre: nombre(n), modo: modoDe(n), mensaje,
    esperando: () => estadoDe(n).porRevisar,
    // Los textos de la pestaña (botón, aviso, confirmación) pasan al modo nuevo.
    alGuardar: () => refrescarEstado(),
  }), mensaje];
}

/** La pestaña Revisar: las correcciones de una instancia (revision.js). */
function vistaRevisar() {
  alCambiarDatos = () => {};
  return pestanaRevisar({
    semestre, ciclo: estadoCurso || null, id: revisarId,
    // Cambiar el interruptor de una instancia cambia los textos de Evaluar.
    alCambiarModo: () => refrescarEstado(),
    alCambiarId: (n) => {
      revisarId = n;
      if (pestana.id === "revisar") history.replaceState(null, "", hashDe("revisar"));
    },
    // Un envío o un descarte cambia los números de las pestañas y de la línea de arriba.
    alCambiar: () => refrescarEstado(),
  });
}

function dibujar() {
  const resultado = el("div", { id: "resultado" });
  pintarCabecera();
  app.replaceChildren(
    el("div", { class: "cabeza-operacion" }, chipSemestre(semestre)),
    zonaEstado, zonaPestanas,
    ...(pestana.revisar ? [vistaRevisar()] : formulario(pestana, resultado).filter(Boolean)),
    resultado, el("hr"), historial.nodo);
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
