// Prueba las cuentas del historial de prompts (public/historial-prompts.js):
// qué versiones tiene cada prompt, en qué semanas o tareas se usó cada una,
// el orden y el diff. La corre pruebas/web.py, que además pasa un texto y la
// huella que le calcula modulos/ia/versiones.py, para compararla.
const h = await import(new URL("../public/historial-prompts.js", import.meta.url));

let fallas = 0;
const check = (nombre, ok) => { console.log(`${ok ? "OK" : "FALLA"}\t${nombre}`); if (!ok) fallas++; };

// --- versiones de un prompt
const archivos = [
  { ruta: "tests_semanales/prompts/evaluar_respuesta.md" },
  { ruta: "tests_semanales/prompts_usados/evaluar_respuesta@aaaaaaaa.md", subido: "2099-03-01T10:00:00Z" },
  { ruta: "tests_semanales/prompts_usados/evaluar_respuesta@bbbbbbbb.md", subido: "2099-04-01T10:00:00Z" },
  { ruta: "tests_semanales/prompts_usados/pauta@cccccccc.md" },
  { ruta: "tests_semanales/prompts_usados/tutoria@dddddddd.md" },
  { ruta: "tareas/prompts_usados/evaluar_respuesta@eeeeeeee.md" },
  { ruta: "tests_semanales/prompts_usados/evaluar_respuesta@1234.md" },
  { ruta: "tests_semanales/prompts_usados/evaluar_respuesta@ffffffff.md.bak" },
];
const v = h.versionesDe("tests_semanales/prompts/evaluar_respuesta.md", archivos);
check("las versiones son las del mismo prompt y del mismo flujo",
  JSON.stringify(v.map((x) => x.huella)) === '["aaaaaaaa","bbbbbbbb"]' && v[1].subido === "2099-04-01T10:00:00Z");
check("también con rutas sueltas", h.versionesDe("tareas/prompts/corregir_respuesta.md",
  ["tareas/prompts_usados/corregir_respuesta@12345678.md", "tareas/prompts/corregir_respuesta.md"])[0]?.huella === "12345678");
check("un prompt sin versiones no tiene lista", h.versionesDe("tests_semanales/prompts/correo_pregunta.md", archivos).length === 0);

// --- usos según el log
const log = [
  ...[1, 2, 3, 5].map((s) => ({ Flujo: "test", Evento: "evaluacion", Item: String(s), Timestamp: `2099-0${s}-10T10:00:00-03:00`,
    Versiones: "evaluar_respuesta.md@aaaaaaaa; pauta.md@00000001; temperatura=0.2; correo_correccion.md@1234abcd" })),
  { Flujo: "test", Evento: "tutoria", Item: "6", Timestamp: "2099-06-02T09:00:00-03:00", Versiones: "tutoria.md@dddddddd; evaluar_respuesta.md@aaaaaaaa" },
  { Flujo: "test", Evento: "evaluacion", Item: "7", Timestamp: "2099-07-10T10:00:00-03:00", Versiones: "evaluar_respuesta.md@bbbbbbbb" },
  { Flujo: "test", Evento: "evaluacion", Item: "8", Timestamp: "", Versiones: "candidato@bbbbbbbb" },
  { Flujo: "test", Evento: "evaluacion", Item: "9", Timestamp: "2099-09-10T10:00:00-03:00", Versiones: "evaluar_respuesta.md@sin-registro" },
  { Flujo: "tarea", Evento: "evaluacion", Item: "T1", Timestamp: "2099-10-10T10:00:00-03:00", Versiones: "evaluar_respuesta.md@aaaaaaaa" },
];
const usos = h.usosPorHuella("tests_semanales/prompts/evaluar_respuesta.md", log);
check("semanas de cada huella, con cualquier evento que la traiga",
  JSON.stringify(usos.aaaaaaaa.items) === "[1,2,3,5,6]" && usos.aaaaaaaa.eventos === 5
  && JSON.stringify(usos.bbbbbbbb.items) === "[7]");
check("primer y último uso", usos.aaaaaaaa.primero === "2099-01-10T10:00:00-03:00"
  && usos.aaaaaaaa.ultimo === "2099-06-02T09:00:00-03:00");
check("ni candidatos ni sin-registro ni otro flujo", Object.keys(usos).sort().join() === "aaaaaaaa,bbbbbbbb");
check("la plantilla del correo se cuenta aparte",
  h.usosPorHuella("tests_semanales/prompts/correo_correccion.md", log)["1234abcd"]?.eventos === 4);

const logTareas = [
  { Flujo: "tarea", Evento: "evaluacion", Item: "T2", Timestamp: "2099-05-02T10:00:00-03:00",
    Versiones: "corregir_respuesta.md@12345678; pauta.md@1; escala=1.0-7.0; correo_feedback.md@9999aaaa" },
  { Flujo: "tarea", Evento: "evaluacion", Item: "T10", Timestamp: "2099-07-02T10:00:00-03:00", Versiones: "corregir_respuesta.md@12345678" },
  { Flujo: "tarea", Evento: "evaluacion", Item: "T1", Timestamp: "2099-04-02T10:00:00-03:00", Versiones: "corregir_respuesta.md@12345678" },
  { Flujo: "tarea", Evento: "evaluacion", Item: "T1", Timestamp: "2099-04-03T10:00:00-03:00", Versiones: "corregir_respuesta.md@87654321" },
];
const usosT = h.usosPorHuella("tareas/prompts/corregir_respuesta.md", logTareas);
check("usos de tareas, T2 antes que T10", JSON.stringify(usosT["12345678"].items) === '["T1","T2","T10"]'
  && usosT["12345678"].ultimo === "2099-07-02T10:00:00-03:00");
check("texto de usos de tareas", h.textoUsos(usosT["12345678"]) === "T1, T2 y T10"
  && h.textoUsos({ items: ["T1", "T2"] }) === "T1 y T2" && h.textoUsos({ items: ["T1", "T2", "T3", "T5"] }) === "T1 a T3 y T5");
check("texto de usos de semanas", h.textoUsos({ items: [1, 2, 3, 5] }) === "semanas 1 a 3 y 5"
  && h.textoUsos({ items: [4] }) === "semana 4" && h.textoUsos({ items: [1, 2] }) === "semanas 1 y 2");
check("dos seguidas son dos elementos de la enumeración", h.textoUsos({ items: [1, 2, 4, 5] }) === "semanas 1, 2, 4 y 5"
  && h.textoUsos({ items: [1, 2, 5, 6, 8, 9] }) === "semanas 1, 2, 5, 6, 8 y 9"
  && h.textoUsos({ items: [1, 2, 3, 5, 6] }) === "semanas 1 a 3, 5 y 6"
  && h.textoUsos({ items: ["T1", "T2", "T4", "T5"] }) === "T1, T2, T4 y T5");
check("sin usos", h.textoUsos(undefined) === "sin usos registrados en el log" && h.textoUsos({ items: [] }) === "sin usos registrados en el log");
check("el log se lee desde el CSV", h.filasDelLog("Timestamp,Flujo,Item,Versiones\r\n2099-01-01,test,1,\"a.md@12345678; b\"\r\n")[0].Versiones
  === "a.md@12345678; b");

// --- orden
const orden = h.ordenarVersiones([
  { huella: "11111111", subido: "2099-01-01T00:00:00Z" }, { huella: "aaaaaaaa" },
  { huella: "22222222", subido: "2099-02-01T00:00:00Z" }, { huella: "bbbbbbbb" },
], usos);
check("de la última usada a la más vieja, las sin usos al final",
  orden.map((x) => x.huella).join() === "bbbbbbbb,aaaaaaaa,22222222,11111111");
check("sin log, la subida más nueva primero", h.ordenarVersiones([{ huella: "11111111", subido: "2099-01-01T00:00:00Z" },
  { huella: "22222222", subido: "2099-02-01T00:00:00Z" }]).map((x) => x.huella).join() === "22222222,11111111");

// --- diff
const tipos = (d) => d.bloques.map((x) => `${x.tipo}:${x.lineas.join("|")}`).join(" / ");
const d1 = h.diffLineas("uno\r\ndos\r\ntres\r\ncuatro\r\n", "uno\ndos\nTRES\ncuatro\ncinco");
check("diff: cambiar una línea es quitarla y agregar la nueva, sin ver los \\r",
  tipos(d1) === "igual:uno|dos / quita:tres / agrega:TRES / igual:cuatro / agrega:cinco" && d1.aviso === null);
check("diff de textos iguales", tipos(h.diffLineas("a\nb", "a\r\nb\r\n")) === "igual:a|b");
check("diff desde y hacia vacío", tipos(h.diffLineas("", "a\nb")) === "agrega:a|b" && tipos(h.diffLineas("a", "")) === "quita:a"
  && h.diffLineas("", "").bloques.length === 0);
const d2 = h.diffLineas("a\nb\nc\nd\ne", "a\nc\nx\nd\ne\nf");
check("diff con la subsecuencia común más larga", tipos(d2) === "igual:a / quita:b / igual:c / agrega:x / igual:d|e / agrega:f");
check("contar cambios", JSON.stringify(h.contarCambios(d2.bloques)) === '{"agregadas":2,"quitadas":1}');
const grande = (k) => Array.from({ length: 3000 }, (_, i) => `línea ${k} ${i}`).join("\n");
const inicio = Date.now();
const d3 = h.diffLineas(`igual\n${grande("a")}\nfin`, `igual\n${grande("b")}\nfin`);
check("diff de textos enormes: no se cuelga y avisa", Date.now() - inicio < 2000 && d3.aviso
  && tipos({ bloques: [d3.bloques[0], d3.bloques.at(-1)] }) === "igual:igual / igual:fin"
  && JSON.stringify(h.contarCambios(d3.bloques)) === '{"agregadas":3000,"quitadas":3000}');
check("con un tope chico también degrada", h.diffLineas("a\nb", "c\nd", { tope: 4 }).aviso !== null);
// Cientos de miles de líneas: push(...lista) reventaba la pila en vez de degradar.
const sinExcepcion = (f) => { try { return f(); } catch { return null; } };
const muchas = (k, n) => Array.from({ length: n }, (_, i) => `${k} ${i}`).join("\n");
const d4 = sinExcepcion(() => h.diffLineas(muchas("a", 200000), muchas("b", 10)));
check("diff de 200 mil líneas contra 10: avisa sin reventar", d4 !== null && d4.aviso !== null
  && JSON.stringify(h.contarCambios(d4.bloques)) === '{"agregadas":10,"quitadas":200000}');
const iguales = muchas("igual", 150000);
const d5 = sinExcepcion(() => h.diffLineas(`x\n${iguales}`, `y\n${iguales}`));
check("diff con 150 mil líneas iguales al final no revienta", d5 !== null
  && tipos({ bloques: d5.bloques.slice(0, 2) }) === "quita:x / agrega:y" && d5.bloques.at(-1).lineas.length === 150000);

// --- huella, igual que Python
check("la huella del navegador es la misma que la de Python",
  await h.huella("Corrige con la pauta.\r\nNOTA FINAL: 1 a 7 ñ\r\n\r\n") === "e93a98b5");
const [texto, dePython] = process.argv.slice(2);
if (texto !== undefined) {
  check("la huella de un texto que calculó modulos/ia/versiones.py", await h.huella(texto) === dePython);
}

if (fallas) { console.log(`${fallas} fallas`); process.exit(1); }
console.log("todo OK");
