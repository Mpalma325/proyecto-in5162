// El gasto en la API (public/consumo.js) y en qué va el curso (public/ciclo.js).
// La corre pruebas/web.py, que le pasa una línea de consumo escrita por el
// Python de verdad (modulos/ia/cliente.py): si alguien cambia su forma sin
// cambiar el lector, esta prueba lo dice.
//
//   node probar-consumo.mjs "<línea de consumo>"
const C = await import(new URL("../public/consumo.js", import.meta.url));
const { armarCiclo } = await import(new URL("../public/ciclo.js", import.meta.url));

let fallas = 0;
const check = (nombre, ok, detalle = "") => {
  if (!ok) fallas++;
  console.log(`${ok ? "OK" : "FALLA"}\t${nombre}${ok || !detalle ? "" : ` → ${detalle}`}`);
};

// ---------------------------------------------------------------- consumo
const delPython = process.argv[2] || "";
const leido = C.leerConsumo(`✓ algo\n${delPython}\nmás salida`);
check("lee la línea que escribe modulos/ia/cliente.py", leido.length === 1 && leido[0].modelo === "gpt-prueba"
  && leido[0].llamadas === 2 && leido[0].entrada === 4900 && leido[0].salida === 1250, JSON.stringify(leido));
check("una llamada sola también se lee", C.leerConsumo("Consumo de API (m): 1 llamada, 10 tokens de entrada, 5 de salida.")
  .length === 1);
const precios = C.leerPrecios('{"a": [1, 2]}');
const total = C.sumarConsumo([{ modelo: "a", llamadas: 1, entrada: 1e6, salida: 1e6 },
  { modelo: "b", llamadas: 2, entrada: 10, salida: 10 }], precios);
check("suma los dólares de los modelos con precio", Math.abs(total.usd - 3) < 1e-9, String(total.usd));
check("y dice cuáles no tienen precio", JSON.stringify(total.sinPrecio) === '["b"]', JSON.stringify(total.sinPrecio));
check("precios ilegibles no rompen la página", JSON.stringify(C.leerPrecios("{malo")) === "{}");

// La línea de hoy, también del Python: con caché y con el US$ de ese momento.
const conCache = C.leerConsumo(process.argv[4] || "")[0];
check("lee la caché y el US$ de la línea del Python", conCache?.cache === 6144 && conCache.entrada === 7512
  && conCache.salida === 1830 && Math.abs(conCache.usd - 0.009722) < 1e-9, JSON.stringify(conCache));
const viejo = C.leerConsumo("Consumo de API (gpt-prueba): 2 llamadas, 4900 tokens de entrada, 1250 de salida.")[0];
check("una línea vieja no trae caché ni US$", viejo.cache === 0 && viejo.usd === null, JSON.stringify(viejo));
const cuatro = C.leerConsumo("Consumo de API (m): 1 llamada, 10 tokens de entrada, 5 de salida, US$ 0,0042.")[0];
check("una línea con US$ de cuatro decimales también se lee", cuatro?.usd === 0.0042, JSON.stringify(cuatro));
// Otro precio hoy: el trabajo con US$ queda igual, el viejo se calcula con el de hoy.
const hoy = { "gpt-prueba": [10, 20, 1] };
const mezcla = C.sumarConsumo([conCache, viejo], hoy);
check("cambiar un precio no cambia lo que costó un trabajo con US$",
  Math.abs(C.sumarConsumo([conCache], hoy).usd - 0.009722) < 1e-9);
check("la línea sin US$ se calcula con los precios de hoy",
  Math.abs(mezcla.usd - (0.009722 + (4900 * 10 + 1250 * 20) / 1e6)) < 1e-9 && mezcla.delMomento === 1 && mezcla.deHoy === 1,
  JSON.stringify(mezcla));
check("y la suma avisa que mezcla los dos", C.notaMezcla(mezcla) !== "" && C.notaMezcla(C.sumarConsumo([conCache], hoy)) === ""
  && C.textoConsumo(mezcla).includes(C.notaMezcla(mezcla)), C.textoConsumo(mezcla));
check("la caché y el aviso van en un solo paréntesis",
  C.textoConsumo(mezcla).endsWith(`tokens (6.144 en caché; ${C.notaMezcla(mezcla)})`), C.textoConsumo(mezcla));
check("tarifa con [entrada, salida]: la caché se cobra como entrada",
  JSON.stringify(C.tarifa([1, 2])) === '{"entrada":1,"salida":2,"cache":1}');
check("tarifa con [entrada, salida, caché]", JSON.stringify(C.tarifa([1, 2, 0.1])) === '{"entrada":1,"salida":2,"cache":0.1}');
check("tarifa rechaza otras formas", [[1], [1, 2, 3, 4], [1, -2], ["1", 2], null].every((p) => C.tarifa(p) === null));
check("costo cobra la caché a su precio, nunca más que la entrada",
  Math.abs(C.costo({ entrada: 1e6, cache: 4e5, salida: 0 }, C.tarifa([1, 2, 0.1])) - 0.64) < 1e-12
  && Math.abs(C.costo({ entrada: 100, cache: 500, salida: 0 }, C.tarifa([1, 2, 0.1])) - 1e-5) < 1e-15);
check("los centavos de un trabajo no se pierden", C.formatoUsd(0.0042) === "US$ 0,0042", C.formatoUsd(0.0042));
check("montos grandes con dos decimales", C.formatoUsd(12.5) === "US$ 12,50", C.formatoUsd(12.5));

// ---------------------------------------------------------------- en qué va el curso
const notas = [
  "Correo,Flujo,Item,Enviado,Respondio,Nota,Originalidad",
  "a@x.cl,test,9,2026-10-09T09:00:00-03:00,2026-10-12T10:00:00-03:00,\"6,0\",Alta",
  "b@x.cl,test,9,2026-10-09T09:00:00-03:00,2026-10-12T10:00:00-03:00,,",
  "a@x.cl,test,10,2026-10-16T09:00:00-03:00,,,",
  "b@x.cl,test,10,2026-10-16T09:00:00-03:00,,,",
].join("\n");
const preguntas = [
  "Semana,Tema,Fecha de Entrega,Control P1,Control P2,Control P3,Control Pauta P1,Control Pauta P2,Control Pauta P3,"
    + "Tratamiento P1,Tratamiento P2,Tratamiento P3,Tratamiento Pauta P1,Tratamiento Pauta P2,Tratamiento Pauta P3",
  '10,Tema,"lunes 19/10/2026, 10:15",¿P?,,,pauta,,,,,,,,',
  "11,Otro,,¿P?,,,pauta,,,,,,,,",
].join("\n");
const c = armarCiclo(notas, ["tests_semanales/data/resumen_semana_9.txt"], preguntas);
const viernes = new Date(2026, 9, 17, 12, 0);
const p = c.proximoPaso(viernes);
check("con la semana 10 enviada y sin notas, toca evaluarla", p.paso === "evaluar" && p.semana === 10, JSON.stringify(p));
check("cuando cierre su entrega, no antes", p.ya === false && p.cuando?.getDate() === 19, JSON.stringify(p));
check("el lunes después de las 10:15 ya toca", c.proximoPaso(new Date(2026, 9, 19, 11, 0)).ya === true);
check("cuenta las respuestas sin nota", c.sinNota() === 1, String(c.sinNota()));
check("ve el resumen de la semana 9", c.conResumen.has(9));
const evaluada = armarCiclo(notas.replace(/,,,\n/, ',2026-10-19T09:00:00-03:00,"5,0",Media\n'), [], preguntas);
const q = evaluada.proximoPaso(new Date(2026, 9, 20));
check("con la 10 evaluada, toca enviar la 11 una semana después de la 10", q.paso === "enviar" && q.semana === 11
  && q.cuando?.getDate() === 23, JSON.stringify(q));
check("sin notas.csv (semestre nuevo), toca enviar la semana 1",
  armarCiclo("", [], preguntas.replace("10,Tema", "1,Tema")).proximoPaso().semana === 1);

// ---------------------------------------------------------------- trabajos fallidos que quedan pendientes
const { fallidosSinResolver } = await import(new URL("../public/comun.js", import.meta.url));
const tr = (id, flujo, semana, estado, prueba, creado) => ({ id, flujo, argumentos: { semana }, estado, prueba, creado });
const lista = [
  tr("a", "tests.evaluar", 9, "fallido", 0, "2026-10-13T10:00:00Z"),
  tr("b", "tests.evaluar", 9, "terminado", 0, "2026-10-13T10:20:00Z"),
  tr("c", "tests.evaluar", 10, "fallido", 1, "2026-10-14T10:00:00Z"),
  tr("d", "tests.enviar", 11, "fallido", 0, "2026-10-15T10:00:00Z"),
  tr("e", "tests.enviar", 11, "terminado", 1, "2026-10-15T10:10:00Z"),
  tr("f", "tests.resumen", 8, "fallido", 1, "2026-10-15T11:00:00Z"),
];
const ids = fallidosSinResolver(lista).map((t) => t.id);
check("un fallo real que después se repitió bien ya no se marca", !ids.includes("a"), JSON.stringify(ids));
check("una simulación fallida no se marca (no hizo nada)", !ids.includes("c"), JSON.stringify(ids));
check("un envío real fallido sigue marcado si solo se simuló después", ids.includes("d"), JSON.stringify(ids));
check("un resumen fallido se marca (escribe aunque no mande correos)", ids.includes("f"), JSON.stringify(ids));
const repetidos = fallidosSinResolver([
  { id: "s1", flujo: "datos.sabana", argumentos: {}, estado: "fallido", prueba: 0, creado: "2026-11-01T10:00:00Z" },
  { id: "s2", flujo: "datos.sabana", argumentos: {}, estado: "fallido", prueba: 0, creado: "2026-11-01T10:05:00Z" },
  { id: "s3", flujo: "datos.sabana", argumentos: {}, estado: "fallido", prueba: 0, creado: "2026-11-01T10:02:00Z" },
]);
check("varios fallos del mismo trabajo son una línea, con el intento más nuevo",
  repetidos.length === 1 && repetidos[0].id === "s2" && repetidos[0].intentos === 3, JSON.stringify(repetidos));

// ---------------------------------------------------------------- la barra de avance
// Lo que imprime modulos/progreso.py al recorrer tres respuestas.
const { progresoDe, sinProgreso } = await import(new URL("../public/comun.js", import.meta.url));
const avance = process.argv[3] || "";
const mitad = avance.split("\n").slice(0, 5).join("\n"); // 0/3, ✓, 1/3, ✓, 2/3
check("lee cuántos van de cuántos", JSON.stringify(progresoDe(mitad)) === '{"hechos":2,"total":3,"unidad":"respuestas"}',
  JSON.stringify(progresoDe(mitad)));
check("al terminar, van todos", progresoDe(avance)?.hechos === 3, JSON.stringify(progresoDe(avance)));
check("las líneas de avance no se muestran ni dejan huecos",
  sinProgreso(avance) === "✓ una respuesta\n✓ una respuesta\n✓ una respuesta\n", JSON.stringify(sinProgreso(avance)));
check("una salida sin avance no tiene barra", progresoDe("✓ algo\n") === null);

const { avanceDe } = await import(new URL("../public/comun.js", import.meta.url));
const ahora = Date.parse("2026-10-22T20:00:20Z");
const corriendo = { id: "x", flujo: "tests.evaluar", prueba: 0, estado: "corriendo", creado: "2026-10-22T20:00:00Z" };
const mitadDeDiez = avanceDe(corriendo, { hechos: 5, total: 10, unidad: "respuestas" }, ahora);
check("a la mitad en 20 s, quedan ~20 s", mitadDeDiez?.pct === 50 && mitadDeDiez.texto === "5/10 respuestas · quedan ~20 s",
  JSON.stringify(mitadDeDiez));
check("sin avance ni historial no inventa un tiempo", avanceDe(corriendo, null, ahora) === null);
check("al terminar muestra lo hecho, sin tiempo", avanceDe({ ...corriendo, estado: "cancelado" },
  { hechos: 3, total: 10, unidad: "correos" }, ahora)?.texto === "3/10 correos");

process.exit(fallas ? 1 : 0);
