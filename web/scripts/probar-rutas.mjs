// Prueba la regla RUTA_VALIDA de src/index.ts, leyéndola del archivo tal cual.
// Tiene que aceptar los nombres raros de U-Cursos y rechazar todo lo que
// permita salirse de la carpeta del semestre. La corre pruebas/web.py.
import { readFileSync } from "node:fs";

const fuente = readFileSync(new URL("../src/index.ts", import.meta.url), "utf8");
const linea = fuente.split("\n").find((l) => l.startsWith("const RUTA_VALIDA"));
const R = eval(linea.replace("const RUTA_VALIDA = ", "").replace(/;\s*$/, ""));

const casos = [
  ["alumnos.csv", true, "un archivo normal"],
  ["tareas/data/entregas/T1/T1-Contreras, Del Pino, Urrutia.html", true, "comas en el nombre"],
  ["tareas/data/entregas/T1/Tarea_1_Cofré_Loyola.html", true, "acento escrito aparte"],
  ["tareas/data/entregas/T1/Tarea_1_Cofre╠ü_Loyola.html", true, "nombre mal decodificado"],
  ["../alumnos.csv", false, "subir de carpeta"],
  ["tareas/../../x", false, "subir de carpeta en medio"],
  ["/etc/passwd", false, "barra inicial"],
  ["tareas//x", false, "barra doble"],
  ["tareas\\x", false, "barra invertida"],
  ["a:b.csv", false, "dos puntos (Windows)"],
  ["a\u0000b", false, "carácter de control"],
  ["", false, "vacía"],
  ["x".repeat(301), false, "demasiado larga"],
];
let mal = 0;
for (const [ruta, esperado, nombre] of casos) {
  const ok = R.test(ruta) === esperado;
  console.log(`${ok ? "OK" : "FALLA"}\t${esperado ? "acepta" : "rechaza"} ${nombre}`);
  if (!ok) mal++;
}
process.exit(mal ? 1 : 0);
