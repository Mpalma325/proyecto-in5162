// Prueba urlTrabajos() de public/comun.js y la validación del Worker para
// /api/trabajos (prefijo de flujo y límite). La corre pruebas/web.py.
import fs from "node:fs";

const comun = fs.readFileSync(new URL("../public/comun.js", import.meta.url), "utf-8");
const ini = comun.indexOf("const HISTORIAL_INICIAL");
const fin = comun.indexOf("export function historialTrabajos");
const urlTrabajos = new Function(`${comun.slice(ini, fin).replace("export function", "function")}\nreturn urlTrabajos;`)();
const worker = fs.readFileSync(new URL("../src/index.ts", import.meta.url), "utf-8");
const prefijo = new RegExp(worker.match(/const PREFIJO_FLUJO = \/(.+)\/;/)[1]);

const casos = [
  ["sin prefijo ni límite, la URL de siempre", urlTrabajos("2026-2") === "/api/trabajos?semestre=2026-2"],
  ["con prefijo pide solo esos flujos", urlTrabajos("2026-2", "tareas.") === "/api/trabajos?semestre=2026-2&flujo=tareas."],
  ["Ver más manda el límite", urlTrabajos("2026-2", "tests.", 90) === "/api/trabajos?semestre=2026-2&flujo=tests.&limite=90"],
  ["el Worker acepta tareas., tests. y tests.experimento",
    ["tareas.", "tests.", "tests.experimento"].every((p) => prefijo.test(p))],
  ["el Worker rechaza comodines y comillas", !["%", "tareas.%", "x'", "Tareas."].some((p) => prefijo.test(p))],
  ["el Worker limita a 120", /LIMITE_TRABAJOS_MAX = 120;/.test(worker)],
  ["solo pendientes: la URL lo pide y no manda límite",
    urlTrabajos("2026-2", "tests.", undefined, true) === "/api/trabajos?semestre=2026-2&flujo=tests.&pendientes=1"],
  ["el Worker filtra los pendientes por estado, fuera de la ventana del historial",
    /estado = 'pendiente'/.test(worker) && /searchParams\.get\("pendientes"\) === "1"/.test(worker)],
];
for (const [nombre, ok] of casos) console.log(`${ok ? "OK" : "FALLA"}\t${nombre}`);
process.exit(casos.every(([, ok]) => ok) ? 0 : 1);
