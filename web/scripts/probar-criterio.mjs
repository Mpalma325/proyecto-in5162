// Prueba las cuentas de Probar criterio (public/criterio.js): el costo
// estimado, en qué semanas se usó cada versión del prompt y el resumen de una
// comparación. La corre pruebas/web.py.
const c = await import(new URL("../public/criterio.js", import.meta.url));

let fallas = 0;
const check = (nombre, ok) => { console.log(`${ok ? "OK" : "FALLA"}\t${nombre}`); if (!ok) fallas++; };

// --- costo
const consumos = [
  { flujo: "tests.evaluar", prueba: 0, usos: [{ modelo: "gpt-5.4-mini", llamadas: 10, entrada: 30000, salida: 8000 }] },
  { flujo: "tests.evaluar", prueba: 1, usos: [{ modelo: "otro", llamadas: 99, entrada: 1, salida: 1 }] },
  { flujo: "tests.resumen", prueba: 0, usos: [{ modelo: "otro", llamadas: 5, entrada: 9e6, salida: 9e6 }] },
  { flujo: "tests.experimento", prueba: 0, usos: [{ modelo: "gpt-5.4-mini", llamadas: 10, entrada: 32000, salida: 8000 }] },
];
const por = c.consumoPorRespuesta(consumos);
check("el promedio usa solo correcciones reales y pruebas de criterio",
  por && por.llamadas === 20 && por.entrada === 3100 && por.salida === 800 && por.modelo === "gpt-5.4-mini");
check("sin correcciones anteriores no hay estimación", c.consumoPorRespuesta([consumos[1], consumos[2]]) === null);
const precios = { "gpt-5.4-mini": [1, 4] };
const igual = c.estimarCosto({ n: 10, porRespuesta: por, largoCandidato: 1000, largoVigente: 1000, precios });
check("10 respuestas con un prompt del mismo largo", igual.llamadas === 10 && igual.entrada === 31000
  && igual.salida === 8000 && Math.abs(igual.usd - (31000 * 1 + 8000 * 4) / 1e6) < 1e-12);
const largo = c.estimarCosto({ n: 10, porRespuesta: por, largoCandidato: 5000, largoVigente: 1000, precios });
check("un prompt más largo cuesta más entrada", largo.entrada === 31000 + 10 * 1000);
check("sin precio para el modelo se avisa", c.estimarCosto({ n: 1, porRespuesta: por, largoCandidato: 0,
  largoVigente: 0, precios: {} }).sinPrecio[0] === "gpt-5.4-mini");
// Con caché: 2000 de los 3100 tokens de entrada por respuesta salen de la caché del proveedor.
const conCache = c.consumoPorRespuesta([{ flujo: "tests.evaluar", prueba: 0,
  usos: [{ modelo: "gpt-5.4-mini", llamadas: 10, entrada: 31000, cache: 20000, salida: 8000 }] }]);
check("el promedio trae la caché por respuesta", conCache.cache === 2000);
const barato = c.estimarCosto({ n: 10, porRespuesta: conCache, largoCandidato: 1000, largoVigente: 1000,
  precios: { "gpt-5.4-mini": [1, 4, 0.1] } });
check("la estimación cobra la caché a su precio", barato.cache === 20000
  && Math.abs(barato.usd - (11000 * 1 + 20000 * 0.1 + 8000 * 4) / 1e6) < 1e-12);
const corto = c.estimarCosto({ n: 10, porRespuesta: conCache, largoCandidato: 0, largoVigente: 12000,
  precios: { "gpt-5.4-mini": [1, 4, 0.1] } });
check("la caché nunca pasa de la entrada", corto.cache === corto.entrada);

// --- versiones
check("la huella del prompt sale de la columna Versiones",
  c.huellaDelPrompt("evaluar_respuesta.md@55bb53d6; pauta.md@be668ace; reconstruido") === "55bb53d6"
  && c.huellaDelPrompt("tutoria.md@f4c77fc1; pauta.md@1264ec0f") === null && c.huellaDelPrompt("") === null);
const log = [
  ...[1, 2, 3, 5].map((s) => ({ Flujo: "test", Evento: "evaluacion", Item: String(s), Versiones: "evaluar_respuesta.md@aaaaaaaa" })),
  { Flujo: "test", Evento: "evaluacion", Item: "7", Versiones: "evaluar_respuesta.md@bbbbbbbb; pauta.md@1" },
  { Flujo: "test", Evento: "tutoria", Item: "8", Versiones: "evaluar_respuesta.md@bbbbbbbb" },
  { Flujo: "test", Evento: "evaluacion", Item: "9", Versiones: "" },
];
const semanas = c.semanasPorVersion(log);
check("semanas por versión, solo de evaluaciones", JSON.stringify(semanas) === '{"aaaaaaaa":[1,2,3,5],"bbbbbbbb":[7]}');
check("rangos de semanas", c.rangos([1, 2, 3, 5]) === "1 a 3 y 5" && c.rangos([7]) === "7"
  && c.rangos([1, 2, 4, 5, 6, 9]) === "1, 2, 4 a 6 y 9");

check("la huella del navegador es la misma que la de Python",
  await c.huella("  Criterio A\r\npuntaje ñ 0 a 3\r\n") === "b960f54e");

// --- comparación
const filas = [
  { NotaAntes: "4.0", NotaDespues: "5.5", DeltaNota: "1.5", OriginalidadAntes: "Baja", OriginalidadDespues: "Alta", DeltaNivel: "2", FormatoOK: "SI" },
  { NotaAntes: "6.0", NotaDespues: "6.0", DeltaNota: "0.0", OriginalidadAntes: "Media", OriginalidadDespues: "Media", DeltaNivel: "0", FormatoOK: "SI" },
  { NotaAntes: "7.0", NotaDespues: "", DeltaNota: "", OriginalidadAntes: "Alta", OriginalidadDespues: "", DeltaNivel: "", FormatoOK: "NO" },
  { NotaAntes: "5.0", NotaDespues: "4.5", DeltaNota: "-0.5", OriginalidadAntes: "Media", OriginalidadDespues: "Baja", DeltaNivel: "-1", FormatoOK: "SI" },
];
const r = c.resumirComparacion(filas);
check("total y sin formato", r.total === 4 && r.sinFormato === 1);
check("medias solo de las que tienen las dos notas", r.mediaAntes === 5 && r.mediaDespues === 16 / 3);
check("cuántas notas suben, bajan o quedan igual", r.notas.suben === 1 && r.notas.bajan === 1 && r.notas.iguales === 1);
check("originalidad por categoría", r.antes.Media === 2 && r.antes.Alta === 1 && r.despues.Alta === 1 && r.despues.Baja === 1);
const orden = c.ordenarPorCambio(filas);
check("primero las que más cambiaron, al final las sin nota", orden[0] === filas[0] && orden.at(-1) === filas[2]);
check("notas para mostrar", c.textoNota("6.5") === "6,5" && c.textoNota("5") === "5,0" && c.textoNota("") === "—");

if (fallas) { console.log(`${fallas} fallas`); process.exit(1); }
console.log("todo OK");
