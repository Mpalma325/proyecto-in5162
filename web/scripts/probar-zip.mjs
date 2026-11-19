// Prueba extraerZip() de public/datos.js sin navegador ni JSZip: saca la función
// del archivo y le pasa zips de mentira. Lo mismo que pruebas/entregas_zip.py
// comprueba en Python. La corre pruebas/web.py. Nombres inventados.
import fs from "node:fs";

const fuente = fs.readFileSync(new URL("../public/datos.js", import.meta.url), "utf-8");
const desde = fuente.indexOf("// Además de la metadata de macOS");
const hasta = fuente.indexOf("// El Worker acepta letras");
if (desde < 0 || hasta < 0) {
  console.log("FALLA\tse encuentra extraerZip en datos.js");
  process.exit(1);
}

// Un zip de mentira: {ruta: contenido}; un contenido objeto es un zip anidado.
const zipDe = (miembros) => ({
  files: Object.fromEntries(Object.keys(miembros).map((m) => [m, {}])),
  file: (m) => ({ async: async () => miembros[m] }),
});
const JSZip = { loadAsync: async (x) => x };
const extraerZip = new Function("cargarJsZip",
  `const nombre = (ruta) => ruta.split("/").pop();\n${fuente.slice(desde, hasta)}\nreturn extraerZip;`,
)(async () => JSZip);

const casos = [];
const probar = (nombre, ok, detalle) => casos.push([ok, nombre, detalle]);

// El zip individual que da U-Cursos para un alumno: la carpeta del grupo adentro.
let lote = { archivos: [], omitidos: [] };
await extraerZip(zipDe({
  "t1-Soto/Tarea01.html": "html",
  "t1-Soto/Tarea01.Rmd": "rmd",
  "t1-Soto/datos.csv": "a,b",
}), lote, "", 0, "Soto_Rojas__Bruno_11111111");
let nombres = lote.archivos.map(([n]) => n).sort();
probar("el zip individual deja la entrega con el nombre de U-Cursos, con su .Rmd",
  JSON.stringify(nombres) === JSON.stringify(["Soto_Rojas__Bruno_11111111.Rmd", "Soto_Rojas__Bruno_11111111.html"]),
  nombres);

// El zip general no cambia: un zip por alumno adentro.
lote = { archivos: [], omitidos: [] };
await extraerZip(zipDe({
  "Soto_Rojas__Bruno_11111111.zip": zipDe({ "t1/Tarea01.html": "a", "t1/Tarea01.Rmd": "r" }),
  "Mora_Vidal__Ana_22222222.zip": zipDe({ "t1/Tarea01.html": "b" }),
}), lote, "", 0, "Tarea 1");
nombres = lote.archivos.map(([n]) => n).sort();
probar("el zip general sigue dando un HTML por alumno con su nombre",
  JSON.stringify(nombres) === JSON.stringify(["Mora_Vidal__Ana_22222222.html", "Soto_Rojas__Bruno_11111111.Rmd",
    "Soto_Rojas__Bruno_11111111.html"]), nombres);

// Un zip subido con varios HTML sueltos no toma el nombre del zip.
lote = { archivos: [], omitidos: [] };
await extraerZip(zipDe({ "Grupo1.html": "a", "Grupo2.html": "b" }), lote, "", 0, "Varios");
nombres = lote.archivos.map(([n]) => n).sort();
probar("varios HTML sueltos en el zip subido conservan su nombre",
  JSON.stringify(nombres) === JSON.stringify(["Grupo1.html", "Grupo2.html"]), nombres);

for (const [ok, nombre, detalle] of casos) console.log(`${ok ? "OK" : "FALLA"}\t${nombre}${ok ? "" : ` ${JSON.stringify(detalle)}`}`);
process.exit(casos.every(([ok]) => ok) ? 0 : 1);
