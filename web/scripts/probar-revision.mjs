// Tests › Revisar (public/revision.js) y lo que la acompaña en la página:
// la configuración del semestre, el texto de Confirmar, el ciclo con «por
// revisar», el aviso de Inicio y qué trabajos mandan correos. La corre
// pruebas/web.py, que le pasa lo que calcula el Python de verdad con los
// mismos datos (decisiones.py, feedback.py, ajustar.py, configuracion.py):
//
//   node probar-revision.mjs esperado.json
import fs from "node:fs";

const R = await import(new URL("../public/revision.js", import.meta.url));
const { leerConfiguracion, modoInstancia } = await import(new URL("../public/configuracion.js", import.meta.url));
const P = await import(new URL("../public/preguntas.js", import.meta.url));
const { armarCiclo } = await import(new URL("../public/ciclo.js", import.meta.url));
const { estadoCandidato } = await import(new URL("../public/comun.js", import.meta.url));
const { leerCsv } = await import(new URL("../public/csv.js", import.meta.url));

const esperado = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
let fallas = 0;
const check = (nombre, ok, detalle = "") => {
  if (!ok) fallas++;
  console.log(`${ok ? "OK" : "FALLA"}\t${nombre}${ok || !detalle ? "" : ` → ${detalle}`}`);
};
const j = JSON.stringify;

// ---------------------------------------------------------------- gemelas de Python
esperado.juntar.forEach(({ correccion, decision, sale }, i) => {
  const js = R.juntar(correccion, decision);
  check(`juntar ${i + 1}: la página arma la misma nota, texto y cambios que decisiones.juntar`,
    j(js) === j(sale), `${j(js)} ≠ ${j(sale)}`);
});
esperado.reescribir.forEach(({ html, nota, sale }, i) => {
  const js = R.reescribirNotaFinal(html, nota);
  check(`reescribirNotaFinal ${i + 1}: igual que en Python`, js === sale, `${j(js)} ≠ ${j(sale)}`);
});
esperado.cuerpo.forEach(({ plantilla, html, nombre, sale }, i) => {
  const js = R.cuerpoCorreo(plantilla, html, nombre);
  check(`cuerpo del correo ${i + 1}: el mismo que _construir_cuerpo_correccion`, js === sale, `${j(js)} ≠ ${j(sale)}`);
});
esperado.aviso.forEach(({ plantilla, nombre, nota, motivo, sale }, i) => {
  const js = R.cuerpoAviso(plantilla, nombre, nota, motivo);
  check(`aviso de ajuste ${i + 1}: el mismo que ajustar.cuerpo_aviso`, js === sale, `${j(js)} ≠ ${j(sale)}`);
});
check("sin correo_ajuste.md, el texto fijo es el de ajustar.py", R.AVISO_POR_DEFECTO === esperado.aviso_por_defecto);
esperado.vigente.forEach(({ decision, correccion, sale }, i) => {
  check(`vigente ${i + 1}: ${sale}`, R.vigente(decision, correccion) === sale);
});
esperado.faltante.forEach(({ decision, sale }, i) => {
  const js = R.faltanteManual(decision);
  check(`faltante_manual ${i + 1}: «${sale || "nada"}»`, js === sale, j(js));
});
esperado.configuracion.forEach(({ texto, modo, muestra, instancias }, i) => {
  const c = leerConfiguracion(texto);
  check(`configuracion.json ${i + 1} (${j(texto)?.slice(0, 40)}): ${modo}, ${muestra}, como configuracion.py`,
    c.modo === modo && c.muestra === muestra, j(c));
  // La columna Revision de cada instancia, con ese archivo de respaldo: lo mismo que configuracion.modo_de.
  const js = instancias.map(({ revision }) => modoInstancia(revision, c.modo));
  check(`configuracion.json ${i + 1}: el modo de cada instancia (Revision vacía, auto, revisar, rara) es el de modo_de`,
    j(js) === j(instancias.map((x) => x.modo)), `${j(js)} ≠ ${j(instancias.map((x) => x.modo))}`);
  // Y el ciclo (Inicio, Tests) lo lee igual desde preguntas.csv.
  const filas = instancias.map(({ revision }, k) => `${k + 1},Control,${k + 1},confirmada,,,${revision ?? ""},T,`);
  const ciclo = armarCiclo("", [], ["Instancia,Tipo,Numero,Estado,Envio,Cierre,Revision,Tema,Fecha de Entrega", ...filas]
    .join("\n"), texto);
  const delCiclo = instancias.map((_, k) => ciclo.modoDe(k + 1));
  check(`configuracion.json ${i + 1}: el ciclo da el mismo modo por instancia`,
    j(delCiclo) === j(instancias.map((x) => x.modo)), `${j(delCiclo)} ≠ ${j(instancias.map((x) => x.modo))}`);
});
{
  // Sin la columna Revision (2026-2) ni configuracion.json: todo automático, como antes.
  const sinColumna = armarCiclo("", [], "Instancia,Tipo,Numero,Estado,Envio,Cierre,Tema,Fecha de Entrega\n"
    + "1,Control,1,confirmada,,,T,\n", null);
  const legado = armarCiclo("", [], "Semana,Tema,Fecha de Entrega\n4,T,lunes\n", null);
  check("sin columna Revision ni configuracion.json, automático; el formato antiguo también",
    sinColumna.modoDe(1) === "auto" && legado.modoDe(4) === "auto");
  check("el formato antiguo toma el de configuracion.json", armarCiclo("", [], "Semana,Tema,Fecha de Entrega\n4,T,lunes\n",
    '{"revision": "revisar"}').modoDe(4) === "revisar");
  check("si configuracion.json no se pudo leer y la fila no dice su modo, no se sabe (null)",
    armarCiclo("", [], "Instancia,Tipo,Numero,Estado,Envio,Cierre,Revision,Tema,Fecha de Entrega\n"
      + "1,Control,1,confirmada,,,,T,\n2,Control,2,confirmada,,,auto,T,\n", false).modoDe(1) === null
    && armarCiclo("", [], "Instancia,Tipo,Numero,Estado,Envio,Cierre,Revision,Tema,Fecha de Entrega\n"
      + "1,Control,1,confirmada,,,,T,\n2,Control,2,confirmada,,,auto,T,\n", false).modoDe(2) === "auto");
}

// ---------------------------------------------------------------- el log de una instancia
const log = esperado.log;
const delItem = log.filter((f) => f.Flujo === "test" && f.Item === "4");
const porCorreo = R.estadoPorCorreo(delItem);
const comoPython = Object.fromEntries([...porCorreo].map(([c, e]) => [c, {
  base: R.baseDe(e.correccion), cerrada: e.cerrada, respuesta: e.respuesta?.Timestamp ?? null }]));
check("estado_por_correo: los mismos alumnos, base, cierre y respuesta que en Python",
  j(Object.keys(comoPython).sort().map((c) => [c, comoPython[c]]))
    === j(Object.keys(esperado.estado_por_correo).sort().map((c) => [c, esperado.estado_por_correo[c]])),
  `${j(comoPython)} ≠ ${j(esperado.estado_por_correo)}`);
check("la respuesta duplicada queda aparte, para el aviso «respondió otra vez»",
  porCorreo.get("ana@correo.test")?.duplicados.map((d) => d.Respuesta).join() === "otra respuesta");

const { decisiones } = R.leerDecisiones(esperado.decisiones_texto);
const casos = R.casosDe(log, esperado.notas, decisiones, 4);
const estados = Object.fromEntries(casos.map((c) => [c.correo, c.estado]));
const con = (e) => casos.filter((c) => c.estado === e).map((c) => c.correo).sort();
check("lo que la página muestra con el envío pedido es lo que tests.feedback manda",
  j(con("pedida")) === j(esperado.seleccion.enviar), `${j(con("pedida"))} ≠ ${j(esperado.seleccion.enviar)}`);
check("los descartes sin registrar son los que tests.feedback registra",
  j(con("descarte")) === j(esperado.seleccion.descartar), `${j(con("descarte"))} ≠ ${j(esperado.seleccion.descartar)}`);
const viejas = casos.filter((c) => c.vieja).map((c) => c.correo).sort();
check("una decisión sobre una corrección anterior: la página pide revisar otra vez y el trabajo la salta",
  viejas.length > 0 && viejas.every((c) => esperado.seleccion.saltadas.includes(c)), `${j(viejas)} / ${j(esperado.seleccion.saltadas)}`);
check("estados de la pestaña: por revisar, aprobada, enviada, descartada y la de otra instancia fuera",
  estados["ana@correo.test"] === "por_revisar" && estados["beto@correo.test"] === "enviada"
  && estados["caro@correo.test"] === "pedida" && estados["dani@correo.test"] === "por_revisar"
  && estados["eli@correo.test"] === "descartada" && estados["gabi@correo.test"] === "aprobada"
  && estados["hugo@correo.test"] === "descarte" && !("fede@correo.test" in estados), j(estados));
check("la corrección a mano se marca como del docente; la automática pendiente, como automática",
  casos.find((c) => c.correo === "caro@correo.test")?.manual === true
  && casos.find((c) => c.correo === "ivan@correo.test")?.automatica === true);
const enBloque = R.aprobablesEnBloque(casos).map((c) => c.correo);
check("«Aprobar todas» toma las por revisar sin nada que mirar: no la de quien respondió otra vez (ana) ni la "
  + "corregida otra vez después de la decisión (dani)", j(enBloque) === j(["ivan@correo.test"]), j(enBloque));
const anaCaso = { ...casos.find((c) => c.correo === "ana@correo.test"), duplicados: [] };
check("sin el duplicado, la de ana sí entra", R.aprobablesEnBloque([anaCaso]).length === 1);
check("ni una sin nota, ni una a mano", R.aprobablesEnBloque([
  { ...anaCaso, correccion: { ...anaCaso.correccion, Nota: "", EvaluacionIA: "<p>sin nota</p>" } },
  { ...anaCaso, manual: true }]).length === 0);
const enJson = { ...anaCaso, correccion: { ...anaCaso.correccion, Nota: "", EvaluacionIA: JSON.stringify({
  preguntas: [{ rotulo: "P1", puntaje: 2 }, { rotulo: "P2", puntaje: 3 }], originalidad: "Alta", retroalimentacion: "Bien" }) } };
check("una corrección en JSON con nota entra; si sus bloques no calzan con las preguntas, no",
  R.aprobablesEnBloque([enJson]).length === 1 && R.aprobablesEnBloque([enJson], {}, () => 3).length === 0
  && R.aprobablesEnBloque([enJson], {}, () => 2).length === 1);
const cuenta = R.conteos(casos);
check("conteos por filtro", cuenta.porRevisar === 3 && cuenta.aprobadas === 2 && cuenta.enviadas === 1
  && cuenta.descartadas === 2 && cuenta.descartes === 1, j(cuenta));
check("el rótulo del selector: «Control 2 · 12 por revisar · 3 aprobadas»",
  R.rotuloInstancia("Control 2", { porRevisar: 12, aprobadas: 3 }) === "Control 2 · 12 por revisar · 3 aprobadas");
check("sin nada pendiente dice cuántas se enviaron",
  R.rotuloInstancia("Control 1", { porRevisar: 0, aprobadas: 0, enviadas: 40, descartes: 0 }) === "Control 1 · 40 enviadas");

// Otra instancia (5), cerrada entera, y la 4 con cosas pendientes: la 4 va primero aunque cierre después.
const cierres = { 4: new Date("2026-11-30T10:15:00-03:00"), 5: new Date("2026-11-20T10:15:00-03:00") };
const opciones = R.instanciasParaElegir(log, esperado.notas, new Map([[4, decisiones]]),
  { nombre: (n) => `Control ${n - 2}`, cierre: (n) => cierres[n] });
check("el selector: primero las que tienen algo pendiente, después por cierre",
  j(opciones.map((o) => [o.id, o.pendiente])) === j([[4, true], [5, false]]), j(opciones));
check("el selector nombra la instancia y no muestra el id", opciones[0].rotulo.startsWith("Control 2 · 3 por revisar"),
  opciones[0].rotulo);

// ---------------------------------------------------------------- lo que se guarda
const leido = R.leerDecisiones('{"Ana@Correo.test ": {"estado": "aprobada", "base": "x"}, "otro@correo.test": {"estado": "rara"}}');
check("leerDecisiones: correo en minúsculas, solo estados conocidos, y el objeto entero para guardarlo",
  j(Object.keys(leido.decisiones)) === j(["ana@correo.test"]) && Object.keys(leido.crudo).length === 2);
check("leerDecisiones: un JSON roto se marca ilegible (la página no guarda encima)",
  R.leerDecisiones("{roto").ilegible === true && R.leerDecisiones(null).ilegible === false);
const ana = casos.find((c) => c.correo === "ana@correo.test");
const tal = R.decisionAl("aprobada", ana, {});
check("aprobar sin editar: solo estado y base, sin nota ni texto (sale lo del modelo, byte a byte)",
  tal.estado === "aprobada" && tal.base === ana.correccion.Timestamp && !("nota_legado" in tal) && !("html_legado" in tal),
  j(tal));
const editada = R.decisionAl("enviar", ana, { nota: "6.0", html: R.normalizarHtml(ana.correccion.EvaluacionIA) });
check("aprobar con la nota cambiada: nota_legado con coma, y el texto sin tocar no se guarda",
  editada.nota_legado === "6,0" && !("html_legado" in editada), j(editada));
const caro = casos.find((c) => c.correo === "caro@correo.test");
const manual = R.decisionAl("enviar", caro, { nota: "5,5", html: "<p>Hecha a mano</p>" });
check("una corrección a mano guarda nota y texto, y queda completa para salir",
  manual.manual === true && R.faltanteManual(manual) === "", j(manual));
check("problemaNota: 6,5 sí; 6,55, 0,5 y vacío no",
  R.problemaNota("6,5") === "" && R.problemaNota("6.5") === "" && R.problemaNota("6,55") !== ""
  && R.problemaNota("0,5") !== "" && R.problemaNota(" ") !== "");

// ---------------------------------------------------------------- alrededor
check("Confirmar en automático dice que el feedback sale solo al cierre",
  /se evalúa vie 30\/11 10:15, al cierre, con el feedback por correo/.test(P.textoAlCierre("auto", "vie 30/11 10:15")));
check("Confirmar en revisión dice que las correcciones esperan y el feedback no sale",
  /esperando tu revisión en Tests › Revisar/.test(P.textoAlCierre("revisar", "x"))
  && !/con el feedback por correo/.test(P.textoAlCierre("revisar", "x")));
check("Confirmar sin saber el modo no promete ninguno de los dos", /sale solo o espera tu revisión/.test(P.textoAlCierre(null, "x")));

const preguntas = leerCsv("Instancia,Tipo,Numero,Estado,Envio,Cierre,Tema,Fecha de Entrega\n"
  + "4,Control,2,confirmada,,,A,\n5,control ,2,confirmada,,,B,\n6,Control,3,borrador,,,C,\n");
const repetidos = P.nombresRepetidos(preguntas);
check("dos «Control 2» (con otra mayúscula o un espacio) no se dejan guardar", repetidos.length === 1
  && /control 2 aparece dos veces \(ids 4 y 5\)/i.test(repetidos[0]), j(repetidos));
check("el formato antiguo no se revisa así", P.nombresRepetidos(leerCsv("Semana,Tema\n1,A\n1,B\n")).length === 0);

const notasCsv = "Correo,Flujo,Item,Enviado,Respondio,Nota,Originalidad,Corregido,Logro,Descartada\n"
  + "a@correo.test,test,4,2026-11-01,2026-11-02,,,2026-11-03,,\n"
  + "b@correo.test,test,4,2026-11-01,2026-11-02,\"6,0\",Alta,2026-11-03,,\n"
  + "c@correo.test,test,4,2026-11-01,2026-11-02,,,2026-11-03,,2026-11-04\n"
  + "d@correo.test,test,4,2026-11-01,2026-11-02,,,,,\n"
  + "a@correo.test,test,5,2026-11-01,2026-11-02,,,2026-11-03,,\n";
const ciclo = armarCiclo(notasCsv, [], "");
const s4 = ciclo.estadoDe(4);
check("el ciclo separa por revisar, descartadas y sin corregir", s4.porRevisar === 1 && s4.descartadas === 1
  && s4.evaluadas === 1 && s4.sinNota === 1 && s4.corregidas === 3, j(s4));
check("porRevisar(): [id, cuántas] de cada instancia con correcciones esperando", j(ciclo.porRevisar()) === j([[4, 1], [5, 1]]),
  j(ciclo.porRevisar()));

const inicio = fs.readFileSync(new URL("../public/inicio.js", import.meta.url), "utf-8");
// En Windows el archivo puede venir con CRLF.
const fuenteAviso = inicio.match(/export function avisoPorRevisar[\s\S]*?\r?\n\}\r?\n/)[0];
const avisoPorRevisar = new Function(`${fuenteAviso.replace("export function", "function")}\nreturn avisoPorRevisar;`)();
check("Inicio: «12 correcciones esperando revisión (Control 2).»",
  avisoPorRevisar(12, "Control 2") === "12 correcciones esperando revisión (Control 2).");
check("Inicio: en singular", avisoPorRevisar(1, "Semana 6") === "1 corrección esperando revisión (Semana 6).");

const comun = fs.readFileSync(new URL("../public/comun.js", import.meta.url), "utf-8");
const desde = comun.indexOf("const SIMULABLES");
const hasta = comun.indexOf("/** \"real\" en rojo");
const mandaCorreos = new Function(`${comun.slice(desde, hasta).replaceAll("export ", "")}\nreturn mandaCorreos;`)();
check("el ajuste con aviso cuenta como trabajo que manda correos",
  mandaCorreos({ flujo: "datos.ajustar", prueba: false, argumentos: { avisar: true } }) === true);
check("el ajuste sin aviso no", mandaCorreos({ flujo: "datos.ajustar", prueba: false, argumentos: {} }) === false);
check("Mandar feedback de verdad manda correos; simulado no",
  mandaCorreos({ flujo: "tests.feedback", prueba: false, argumentos: {} }) === true
  && mandaCorreos({ flujo: "tests.feedback", prueba: true, argumentos: {} }) === false);
check("los candidatos dicen «por revisar» o «descartada», y los de antes «ya tiene nota»",
  estadoCandidato({ estado: "por revisar" }) === "por revisar" && estadoCandidato({ ya_tiene_nota: "6,0" }) === "ya tiene nota 6,0"
  && estadoCandidato({}) === "");

process.exit(fallas ? 1 : 0);
