// Instancias de test (preguntas.csv con columna Instancia): nombre y número,
// fechas de Santiago, confirmar / volver a borrador / cambiar el cierre con un
// sitio de mentira, lo que no se deja cambiar una vez enviado y en qué va el
// curso sin semanas. La corre pruebas/web.py, que le pasa lo que calcula el
// Python de verdad (asunto, cuerpo y fecha de entrega):
//
//   node probar-instancias.mjs esperado.json
//
// esperado.json: { plantilla, fila: {columna: valor}, asunto, cuerpo: {control, tratamiento},
//                  fechas: {iso: texto} }
import fs from "node:fs";

const { leerCsv, escribirCsv } = await import(new URL("../public/csv.js", import.meta.url));
const P = await import(new URL("../public/preguntas.js", import.meta.url));
const C = await import(new URL("../public/comun.js", import.meta.url));
const { armarCiclo } = await import(new URL("../public/ciclo.js", import.meta.url));

const esperado = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
let fallas = 0;
const check = (nombre, ok, detalle = "") => {
  if (!ok) fallas++;
  console.log(`${ok ? "OK" : "FALLA"}\t${nombre}${ok || !detalle ? "" : ` → ${detalle}`}`);
};
const j = JSON.stringify;

// ---------------------------------------------------------------- la plantilla y el archivo vacío
const plantilla = fs.readFileSync(new URL("../../semestres/_template/tests_semanales/data/preguntas.csv", import.meta.url),
  "utf8");
const vacio = leerCsv(plantilla);
check("la plantilla trae la cabecera nueva, la misma que crea la página", j(vacio.columnas) === j(P.CABECERA_NUEVA),
  j(vacio.columnas));
check("con solo la cabecera: formato nuevo, sin columnas faltantes y sin instancias",
  !P.esLegado(vacio) && P.columnasFaltantes(vacio).length === 0 && P.semanasDe(vacio).length === 0);

// ---------------------------------------------------------------- crear y nombrar
let [d, id] = P.agregarInstancia(vacio, { itemsNotas: [3] });
check("el id nuevo pasa al mayor Item de tests de notas.csv (una borrada que se envió no le pasa sus notas a otra)",
  id === 4, String(id));
let s = P.leerSemana(d, 4);
check("la primera, sin tipo usado antes, es «Instancia 1» en borrador",
  P.nombreDe(s) === "Instancia 1" && s.estado === "borrador", j(s));
[d, id] = P.agregarInstancia(d, { tipo: "Control" });
check("otro tipo empieza en 1: «Control 1», id 5", id === 5 && P.nombreDe(P.leerSemana(d, 5)) === "Control 1");
[d, id] = P.agregarInstancia(d, {});
check("sin decir el tipo, usa el de la última creada: «Control 2»", P.nombreDe(P.leerSemana(d, id)) === "Control 2"
  && id === 6);
[d, id] = P.agregarInstancia(d, { tipo: "control" });
check("el tipo no distingue mayúsculas ni tildes al numerar: «control 3»", P.leerSemana(d, id).numeroTipo === 3);
d = P.quitarInstancia(d, 5);
check("borrar «Control 1» no renumera: el siguiente Control es 4, y «Control 2» sigue siendo 2",
  P.siguienteNumero(d, "Control") === 4 && P.nombreDe(P.leerSemana(d, 6)) === "Control 2");
const comoTest = P.conTipo(d, P.leerSemana(d, 6), "Test");
check("un borrador que cambia de tipo toma el número siguiente de ese tipo", P.nombreDe(comoTest) === "Test 1",
  P.nombreDe(comoTest));
check("y si vuelve a su tipo guardado, recupera su número", P.nombreDe(P.conTipo(d, comoTest, "Control")) === "Control 2");
const texto = escribirCsv(d);
check("lo escrito se vuelve a leer igual (ids, tipos y estados)", j(P.semanasDe(leerCsv(texto)).map((x) => x.nombre))
  === j(["Instancia 1", "Control 2", "control 3"]), j(P.semanasDe(leerCsv(texto)).map((x) => x.nombre)));

// ---------------------------------------------------------------- revisar o no, en cada instancia
let [m, im] = P.agregarInstancia(vacio, { tipo: "Control" });
check("la primera del semestre parte revisando", P.leerSemana(m, im).revision === "revisar", j(P.leerSemana(m, im)));
m = P.conRevision(m, im, "auto");
const [m2, im2] = P.agregarInstancia(m, {});
check("la siguiente toma el modo de la última creada (automático)", P.leerSemana(m2, im2).revision === "auto"
  && P.leerSemana(m2, im).revision === "auto");
const sinModo = P.conRevision(m2, im2, "");
check("si la última no dice el suyo, la nueva toma el de configuracion.json; sin saberlo, revisa",
  P.leerSemana(P.agregarInstancia(sinModo, { respaldo: "auto" })[0], im2 + 1).revision === "auto"
  && P.leerSemana(P.agregarInstancia(sinModo, { respaldo: null })[0], im2 + 1).revision === "revisar");
// Una cabecera nueva de antes del interruptor (la de 2026-2 ya usada en un semestre con instancias).
const cabeceraSinRevision = P.CABECERA_NUEVA.filter((c) => c !== "Revision");
const filaSin = (valores) => cabeceraSinRevision.map((c) => valores[c] ?? "").join(",");
const antiguo = leerCsv([cabeceraSinRevision.join(","),
  filaSin({ Instancia: 1, Tipo: "Control", Numero: 1, Estado: "confirmada", Tema: "A", "Control P1": "¿A?" }),
  filaSin({ Instancia: 2, Tipo: "Control", Numero: 2, Estado: "borrador", Tema: "B", "Control P1": "¿B?" })].join("\n"));
check("un archivo sin la columna Revision: la fila dice vacío (rige configuracion.json)",
  P.leerSemana(antiguo, 1).revision === "" && P.columnasFaltantes(antiguo).length === 0);
const conCol = P.agregarInstancia(antiguo, { respaldo: "auto" })[0];
check("al crear una instancia ahí, la columna se agrega al final y las demás filas quedan vacías",
  conCol.columnas.at(-1) === "Revision" && P.leerSemana(conCol, 1).revision === "" && P.leerSemana(conCol, 3).revision === "auto",
  j(conCol.columnas));
check("guardar sin decir el modo no agrega la columna", !P.escribirSemana(antiguo, 2, P.leerSemana(antiguo, 2))
  .columnas.includes("Revision"));
const guardadaAuto = P.escribirSemana(antiguo, 2, { ...P.leerSemana(antiguo, 2), revision: "auto" });
check("guardar con el interruptor movido la agrega y la escribe, sin tocar la otra fila",
  P.leerSemana(guardadaAuto, 2).revision === "auto" && P.leerSemana(guardadaAuto, 1).revision === "");
const cambiada = P.conRevision(leerCsv(escribirCsv(m2)), im, "revisar");
check("conRevision cambia solo esa celda", P.leerSemana(cambiada, im).revision === "revisar"
  && P.leerSemana(cambiada, im2).revision === "auto" && P.leerSemana(cambiada, im).tipo === "Control");
let falta = "";
try { P.conRevision(m2, 99, "auto"); } catch (e) { falta = e.message; }
check("conRevision de una instancia que no está avisa", /no está/.test(falta), falta);
check("pasar a revisar no pregunta", P.textoCambioRevision("Control 2", "revisar", 4) === null);
const aAuto = P.textoCambioRevision("Control 2", "auto", 0);
check("pasar a automático pregunta, y sin nada esperando no habla de Revisar",
  /Control 2 le llega al alumno por correo apenas queda lista/.test(aAuto) && !/Tests › Revisar/.test(aAuto), aAuto);
const conEspera = P.textoCambioRevision("Control 2", "auto", 3);
check("con correcciones esperando dice cuántas, y que no salen solas",
  /Quedan 3 correcciones esperando en Tests › Revisar/.test(conEspera) && /no salen solas/.test(conEspera)
  && /Aprobar todas/.test(conEspera), conEspera);
check("en singular", /Queda 1 corrección esperando/.test(P.textoCambioRevision("Test 1", "auto", 1)));
const registro = P.cambiosSemana(im, { ...P.leerSemana(m2, im), revision: "revisar" }, P.leerSemana(m2, im));
check("el registro dice el cambio de modo", registro === "Control 1: cambió la revisión (ahora el feedback sale solo)",
  registro);
const esperan = P.enviosDeNotas(["Correo,Flujo,Item,Enviado,Nota,Corregido,Descartada",
  "a@x.cl,test,6,2026-11-23,,2026-11-30,", "b@x.cl,test,6,2026-11-23,\"6,0\",2026-11-30,",
  "c@x.cl,test,6,2026-11-23,,2026-11-30,2026-12-01", "d@x.cl,test,6,2026-11-23,,,", "e@x.cl,test,7,2026-11-23,,2026-11-30,"]
  .join("\n")).esperando;
check("de notas.csv: cuántas esperan revisión por instancia (corregidas sin nota ni descarte)",
  esperan.get(6) === 1 && esperan.get(7) === 1 && esperan.size === 2, j([...esperan]));

// ---------------------------------------------------------------- los dos formatos
const legado = leerCsv(`Semana,Tema,Fecha de Entrega,${P.CABECERA_NUEVA.slice(9).join(",")}\n4,Tema,lunes,¿P?,,,p,,,,,,,,\n`);
check("formato antiguo: «Semana 4», sin estado, todas confirmadas", P.esLegado(legado)
  && P.semanasDe(legado)[0].nombre === "Semana 4" && !("estado" in P.leerSemana(legado, 4)));
check("formato antiguo: el asunto de siempre", P.asuntoDe(P.leerSemana(legado, 4))
  === "Evaluación de Progreso Individual Módulo 4: Tema");
const ambas = leerCsv(`Semana,${P.CABECERA_NUEVA.join(",")}\n`);
check("con Semana e Instancia a la vez, el editor no lo abre", P.columnasFaltantes(ambas).length === 1
  && /no las dos/.test(P.columnasFaltantes(ambas)[0]));

// ---------------------------------------------------------------- el correo, igual que el Python
const fila = esperado.fila;
const archivo = leerCsv(`${P.CABECERA_NUEVA.join(",")}\n${P.CABECERA_NUEVA.map((c) =>
  `"${String(fila[c] ?? "").replaceAll('"', '""')}"`).join(",")}\n`);
const inst = P.leerSemana(archivo, Number(fila.Instancia));
check("asunto «Tipo Numero: Tema», igual que modulos/tests/preguntas.py", P.asuntoDe(inst) === esperado.asunto,
  `${P.asuntoDe(inst)} vs ${esperado.asunto}`);
for (const g of ["control", "tratamiento"]) {
  const { html } = P.correoDe(esperado.plantilla, inst, g, "Ana");
  check(`el correo de ${g} es el que arma enviar.py (sin «de la semana», con el nombre y el número visible)`,
    html === esperado.cuerpo[g], `${html}\n---\n${esperado.cuerpo[g]}`);
}
for (const [iso, textoPy] of Object.entries(esperado.fechas)) {
  check(`textoFecha(${iso}) = texto_fecha del Python`, P.textoFecha(iso) === textoPy, `${P.textoFecha(iso)} vs ${textoPy}`);
}
const conCierre = P.escribirSemana(archivo, inst.numero, { ...inst, cierre: "2026-11-23T10:15:00-03:00" });
check("al guardar, la fecha de entrega sale del cierre", P.leerSemana(conCierre, inst.numero).fecha
  === "lunes 23/11/2026, 10:15", P.leerSemana(conCierre, inst.numero).fecha);
check("y la vuelve a leer fechaEntrega (avisos y ciclo)", P.fechaEntrega("lunes 23/11/2026, 10:15")?.getDate() === 23);

// ---------------------------------------------------------------- hora de Santiago
check("noviembre es horario de verano (-03:00)", P.isoSantiago("2026-11-19T10:15") === "2026-11-19T10:15:00-03:00",
  P.isoSantiago("2026-11-19T10:15"));
check("julio es horario de invierno (-04:00)", P.isoSantiago("2026-07-06T10:15") === "2026-07-06T10:15:00-04:00",
  P.isoSantiago("2026-07-06T10:15"));
check("y de vuelta al campo de la página", P.localSantiago("2026-07-06T10:15:00-04:00") === "2026-07-06T10:15"
  && P.localSantiago("2026-11-19T13:15:00Z") === "2026-11-19T10:15");
check("el instante es el que corresponde", Date.parse(P.isoSantiago("2026-11-19T10:15")) === Date.parse("2026-11-19T13:15:00Z"));
check("un campo vacío no inventa fecha", P.isoSantiago("") === "" && P.localSantiago("") === "" && P.textoFecha("") === "");

// ---------------------------------------------------------------- confirmar
const ahora = Date.parse("2026-11-19T12:00:00-03:00");
const base = { numero: 6, tipo: "Control", numeroTipo: 2, tema: "Logit", estado: "borrador",
  envio: "2026-11-23T10:15:00-03:00", cierre: "2026-11-30T10:15:00-03:00",
  preguntas: [{ control: { texto: "¿P?", pauta: "p" }, tratamiento: { texto: "¿P?", pauta: "p" }, igual: true }] };
check("se confirma con envío futuro y cierre después", P.problemasAlConfirmar(base, { ahora }).length === 0,
  j(P.problemasAlConfirmar(base, { ahora })));
check("sin envío ni cierre, no", P.problemasAlConfirmar({ ...base, envio: "", cierre: "" }, { ahora }).length >= 2);
check("con el envío en el pasado, no (salvo «enviar ahora»)",
  P.problemasAlConfirmar({ ...base, envio: "2026-11-18T10:00:00-03:00" }, { ahora }).some((p) => /ya pasó/.test(p))
  && P.problemasAlConfirmar({ ...base, envio: "" }, { ahora, enviarAhora: true }).length === 0);
check("con el cierre antes del envío, no", P.problemasAlConfirmar({ ...base, cierre: base.envio }, { ahora })
  .some((p) => /después del envío/.test(p)));
check("a 90 días se puede (el Worker la deja esperando en D1)",
  P.problemasAlConfirmar({ ...base, envio: "2027-02-10T10:00:00-03:00", cierre: "2027-02-17T10:00:00-03:00" },
    { ahora }).length === 0);
check(`a más de ${P.PROGRAMAR_HASTA_DIAS} días, no`, P.problemasAlConfirmar({ ...base, cierre: "2027-08-01T10:00:00-04:00" },
  { ahora }).some((p) => /días/.test(p)));
check("sin preguntas, no", P.problemasAlConfirmar({ ...base, preguntas: [] }, { ahora }).some((p) => /preguntas/.test(p)));

/** El sitio de mentira: guarda filas, crea trabajos pendientes y los cancela. */
function sitio({ fallaEn = null } = {}) {
  const trabajos = [];
  const guardados = [];
  const pasos = [];
  let n = 0;
  return {
    trabajos, guardados, pasos,
    guardar: async (x, detalle) => { pasos.push(`guardar ${x.estado}`); guardados.push({ ...x, detalle }); },
    pedir: async (flujo, argumentos) => {
      if (flujo === fallaEn) throw new Error("el sitio respondió 400");
      const t = { id: `t${++n}`, flujo, argumentos, prueba: argumentos.prueba ? 1 : 0, estado: "pendiente" };
      trabajos.push(t);
      pasos.push(`pedir ${flujo}`);
      return t.id;
    },
    cancelar: async (id) => {
      const t = trabajos.find((x) => x.id === id);
      if (t.estado === "pendiente") t.estado = "cancelado";
      pasos.push(`cancelar ${id}`);
    },
  };
}
const w = sitio();
w.trabajos.push({ id: "otra", flujo: "tests.enviar", argumentos: { instancia: 9, prueba: false }, prueba: 0, estado: "pendiente" },
  { id: "sim", flujo: "tests.enviar", argumentos: { instancia: 6, prueba: true }, prueba: 1, estado: "pendiente" });
const ids = await P.confirmarInstancia(base, w);
check("confirmar guarda la fila confirmada", w.guardados.at(-1).estado === "confirmada" && /confirmada/.test(w.guardados.at(-1).detalle));
check("y programa el envío a la hora de Envio y la evaluación a la de Cierre, de verdad",
  j(w.trabajos.filter((t) => ids.includes(t.id)).map((t) => [t.flujo, t.argumentos]))
  === j([["tests.enviar", { instancia: 6, prueba: false, a_las: base.envio }],
    ["tests.evaluar", { instancia: 6, prueba: false, a_las: base.cierre }]]),
  j(w.trabajos.map((t) => [t.flujo, t.argumentos])));
check("guarda antes de programar", j(w.pasos.slice(0, 3)) === j(["guardar confirmada", "pedir tests.enviar", "pedir tests.evaluar"]),
  j(w.pasos));

const vuelta = await P.volverABorrador({ ...base, estado: "confirmada" }, { ...w, trabajos: async () => w.trabajos, enviados: 0 });
check("volver a borrador anula los dos programados de esa instancia",
  vuelta.cancelados === 2 && ids.every((x) => w.trabajos.find((t) => t.id === x).estado === "cancelado"), j(vuelta));
check("y no toca los de otra instancia ni las simulaciones",
  w.trabajos.find((t) => t.id === "otra").estado === "pendiente" && w.trabajos.find((t) => t.id === "sim").estado === "pendiente");
check("guarda el borrador antes de anular (un envío que llegue a su hora encuentra el borrador)",
  w.pasos.indexOf("guardar borrador") < w.pasos.findIndex((p) => p.startsWith("cancelar")), j(w.pasos));

let error = "";
try {
  await P.volverABorrador({ ...base, estado: "confirmada" }, { ...sitio(), trabajos: async () => [], enviados: 12 });
} catch (e) { error = e.message; }
check("una instancia ya enviada no vuelve a borrador", /ya se envió/.test(error), error);
error = "";
try {
  await P.volverABorrador({ ...base, estado: "confirmada" }, { ...sitio(), enviados: 0, trabajos: async () =>
    [{ id: "x", flujo: "tests.enviar", argumentos: { instancia: 6 }, prueba: 0, estado: "corriendo" }] });
} catch (e) { error = e.message; }
check("tampoco si su envío ya está corriendo", /ya se envió/.test(error), error);

const f = sitio({ fallaEn: "tests.evaluar" });
error = "";
try { await P.confirmarInstancia(base, f); } catch (e) { error = e.message; }
check("si no se pudo programar la evaluación, anula el envío y la deja en borrador",
  /400/.test(error) && f.trabajos[0].estado === "cancelado" && f.guardados.at(-1).estado === "borrador", j(f.pasos));

const r = sitio();
await P.confirmarInstancia(base, r);
const nuevoCierre = { ...base, estado: "confirmada", cierre: "2026-12-02T10:15:00-03:00" };
check("cambiar el cierre: se revisa que sea futuro y después del envío",
  P.problemasAlCambiarCierre(nuevoCierre, ahora).length === 0
  && P.problemasAlCambiarCierre({ ...nuevoCierre, cierre: "2026-11-18T10:00:00-03:00" }, ahora).length === 1);
const nuevo = await P.reprogramarCierre(nuevoCierre, { ...r, trabajos: async () => r.trabajos });
const evaluaciones = r.trabajos.filter((t) => t.flujo === "tests.evaluar");
check("y se programa una evaluación nueva a esa hora, anulando la vieja; el envío no se toca",
  evaluaciones.length === 2 && evaluaciones[0].estado === "cancelado"
  && r.trabajos.find((t) => t.id === nuevo).argumentos.a_las === nuevoCierre.cierre
  && r.trabajos.find((t) => t.flujo === "tests.enviar").estado === "pendiente", j(r.trabajos));

check("estado en la lista: borrador, programada, enviada",
  P.estadoInstancia(base).texto === "borrador"
  && P.estadoInstancia({ ...base, estado: "confirmada" }).clase === "programada"
  && P.estadoInstancia({ ...base, estado: "confirmada" }, 30).texto === "enviada a 30");

// ---------------------------------------------------------------- lo enviado queda fijo (R16)
const notas = ["Correo,Flujo,Item,Enviado,Nota", "a@x.cl,test,6,2026-11-23T10:15:03-03:00,",
  "b@x.cl,test,6,2026-11-23T10:15:04-03:00,", "a@x.cl,tarea,7,2026-11-01T10:00:00-03:00,", "c@x.cl,test,8,,"].join("\n");
const envios = P.enviosDeNotas(notas);
check("de notas.csv: cuántos tienen Enviado por instancia, y los Item de tests", envios.enviados.get(6) === 2
  && !envios.enviados.has(8) && j(envios.items.sort()) === j([6, 8]), j([...envios.enviados]));
const antes = leerCsv(texto);
const renombrar = (datos, n, cambios) => P.escribirSemana(datos, n, { ...P.leerSemana(datos, n), ...cambios });
check("Tabla completa: cambiar el nombre o el tema de una enviada no se guarda",
  P.cambiosProhibidos(antes, renombrar(antes, 6, { numeroTipo: 5 }), envios.enviados).length === 1
  && P.cambiosProhibidos(antes, renombrar(antes, 6, { tema: "Otro" }), envios.enviados).length === 1);
check("ni quitarla, ni volverla a borrador",
  P.cambiosProhibidos(antes, P.quitarInstancia(antes, 6), envios.enviados).length === 1
  && P.cambiosProhibidos(renombrar(antes, 6, { estado: "confirmada" }), renombrar(antes, 6, { estado: "borrador" }),
    envios.enviados).length === 1);
check("una que no se ha enviado sí se puede cambiar o quitar",
  P.cambiosProhibidos(antes, P.quitarInstancia(renombrar(antes, 4, { tema: "x" }), 7), envios.enviados).length === 0);
check("el formato antiguo se edita como siempre", P.cambiosProhibidos(legado, { columnas: legado.columnas, filas: [] },
  new Map([[4, 30]])).length === 0);

// ---------------------------------------------------------------- en qué va el curso, sin semanas
const filaCsv = (v) => P.CABECERA_NUEVA.map((c) => v[c] ?? "").map((x) => `"${x}"`).join(",");
const preguntas = [P.CABECERA_NUEVA.join(","),
  filaCsv({ Instancia: 1, Tipo: "Control", Numero: 1, Estado: "confirmada", Envio: "2026-11-02T10:00:00-03:00",
    Cierre: "2026-11-20T10:00:00-03:00", Tema: "A", "Control P1": "¿A?" }),
  filaCsv({ Instancia: 2, Tipo: "Control", Numero: 2, Estado: "confirmada", Envio: "2026-11-03T10:00:00-03:00",
    Cierre: "2026-11-19T18:00:00-03:00", Tema: "B", "Control P1": "¿B?" }),
  filaCsv({ Instancia: 3, Tipo: "Test", Numero: 1, Estado: "confirmada", Envio: "2026-11-25T09:00:00-03:00",
    Cierre: "2026-11-27T09:00:00-03:00", Tema: "C", "Control P1": "¿C?" }),
  filaCsv({ Instancia: 4, Tipo: "Test", Numero: 2, Estado: "borrador", Tema: "D", "Control P1": "¿D?" }),
].join("\n");
const notasCiclo = ["Correo,Flujo,Item,Enviado,Respondio,Nota", "a@x.cl,test,1,2026-11-02T10:00:05-03:00,,",
  "a@x.cl,test,2,2026-11-03T10:00:05-03:00,,"].join("\n");
const c = armarCiclo(notasCiclo, [], preguntas);
const hoy = new Date("2026-11-19T12:00:00-03:00");
const p = c.proximoPaso(hoy);
check("dos abiertas a la vez: toca evaluar la que cierra antes (Control 2), aunque se envió después",
  !c.legado && p.paso === "evaluar" && p.semana === 2 && p.abiertas === 2 && p.ya === false, j(p));
check("con su cierre como fecha de entrega", c.entregaDe(2).fecha?.getTime() === Date.parse("2026-11-19T18:00:00-03:00")
  && c.entregaDe(2).texto === "jueves 19/11/2026, 18:00", j(c.entregaDe(2)));
check("los nombres: «Control 2», sin artículo", c.nombre(2) === "Control 2" && c.mencion(3) === "Test 1");
const conNota = notasCiclo.replace(/,$/gm, ",6.0");
const evaluadas = armarCiclo(conNota, [], preguntas);
const q = evaluadas.proximoPaso(hoy);
check("con todo evaluado, toca enviar la confirmada que sale antes, a la hora de su Envio (no 7 días después)",
  q.paso === "enviar" && q.semana === 3 && q.cuando?.getTime() === Date.parse("2026-11-25T09:00:00-03:00") && !q.ya, j(q));
const soloBorrador = armarCiclo(conNota, [],
  preguntas.split("\n").filter((l) => !l.startsWith('"3"')).join("\n")).proximoPaso(hoy);
check("si solo queda un borrador, se dice que falta confirmarlo", soloBorrador.paso === "enviar"
  && soloBorrador.semana === 4 && soloBorrador.borrador === true, j(soloBorrador));

// ---------------------------------------------------------------- trabajos con instancia
C.nombrarInstancias([[2, "Control 2"]]);
check("el historial dice «Control 2», no el id", C.sobreQue({ instancia: 2 }) === "Control 2"
  && C.sobreQue({ instancia: 7 }) === "instancia 7" && C.sobreQue({ semana: 4 }) === "semana 4");
check("idDe lee instancia o semana", C.idDe({ instancia: 3 }) === 3 && C.idDe({ semana: 5 }) === 5);
const fallidos = C.fallidosSinResolver([
  { id: "a", flujo: "tests.evaluar", argumentos: { instancia: 4 }, estado: "fallido", prueba: 0, creado: "2026-11-01T10:00:00Z" },
  { id: "b", flujo: "tests.evaluar", argumentos: { instancia: 4 }, estado: "terminado", prueba: 0, creado: "2026-11-01T11:00:00Z" },
  { id: "c", flujo: "tests.evaluar", argumentos: { instancia: 5 }, estado: "fallido", prueba: 0, creado: "2026-11-01T10:00:00Z" },
  { id: "d", flujo: "tests.evaluar", argumentos: { instancia: 6 }, estado: "terminado", prueba: 0, creado: "2026-11-01T11:00:00Z" },
]).map((t) => t.id);
check("un fallo de una instancia se resuelve con un éxito de la misma, no de otra", j(fallidos) === j(["c"]), j(fallidos));

process.exit(fallas ? 1 : 0);
