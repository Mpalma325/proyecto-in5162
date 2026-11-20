// Las gemelas de la página: correccion.js, escala.js y el juntar de revision.js.
// La corre pruebas/correccion.py, que le pasa una lista de llamadas y compara
// lo que devuelven con lo que da el Python de verdad (modulos/tests/correccion.py,
// modulos/escala.py, modulos/tests/decisiones.py). pruebas/escala.py la usa
// también para la confirmación de «Guardar y recalcular» con la salida real de
// datos.escala:
//
//   node probar-correccion.mjs llamadas.json
//
// Cada llamada es {"f": "correccion.leer", "args": [...]}. Imprime un JSON con
// el resultado de cada una ({"ok": valor} o {"error": mensaje}). Las fracciones
// salen como "5/6" (o "1"), igual que str(Fraction) en Python.
import fs from "node:fs";

const modulos = {
  correccion: await import(new URL("../public/correccion.js", import.meta.url)),
  escala: await import(new URL("../public/escala.js", import.meta.url)),
  revision: await import(new URL("../public/revision.js", import.meta.url)),
  comun: await import(new URL("../public/comun.js", import.meta.url)),
};

const esFraccion = (v) => v && typeof v === "object" && typeof v.n === "bigint" && typeof v.d === "bigint";

function plano(v) {
  if (esFraccion(v)) return v.d === 1n ? String(v.n) : `${v.n}/${v.d}`;
  if (typeof v === "bigint") return String(v);
  if (Array.isArray(v)) return v.map(plano);
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, plano(x)]));
  return v === undefined ? null : v;
}

const llamadas = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const salida = llamadas.map(({ f, args }) => {
  const [modulo, nombre] = f.split(".");
  const funcion = modulos[modulo]?.[nombre];
  if (typeof funcion !== "function") return { error: `no existe ${f}` };
  try {
    return { ok: plano(funcion(...args)) };
  } catch (e) {
    return { error: e.message };
  }
});
process.stdout.write(JSON.stringify(salida));
