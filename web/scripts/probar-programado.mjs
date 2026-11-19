// Prueba programado() de src/index.ts (el cron de la tutoría) sin Worker: saca
// la función del archivo, le quita los tipos con esbuild y le pasa una base de
// mentira. La corre pruebas/web.py.
import fs from "node:fs";
import { transformSync } from "esbuild";

const fuente = fs.readFileSync(new URL("../src/index.ts", import.meta.url), "utf-8");
const desde = fuente.indexOf("const HORA_RESPONDER_DUDAS");
const hasta = fuente.indexOf("// Detener un trabajo.");
if (desde < 0 || hasta < 0) {
  console.log("FALLA\tse encuentra programado en index.ts");
  process.exit(1);
}
const js = transformSync(fuente.slice(desde, hasta), { loader: "ts" }).code;

async function correr(tutoria, cuando) {
  const pedidos = [];
  const db = {
    prepare: (sql) => ({
      bind: () => db.prepare(sql),
      first: async () => {
        if (sql.includes("TUTORIA_AUTOMATICA")) return tutoria === undefined ? null : { valor: tutoria };
        if (sql.includes("FROM semestres")) return { id: "2099-1" };
        return null;
      },
    }),
  };
  const crearTrabajo = async (_env, semestre, flujo, args) => { pedidos.push({ semestre, flujo, args }); };
  const programado = new Function("crearTrabajo", `${js}\nreturn programado;`)(crearTrabajo);
  await programado({ DB: db }, Date.parse(cuando));
  return pedidos;
}

// En noviembre Santiago está en UTC-3: las 21:00 UTC son las 18:00.
const A_LAS_18 = "2026-11-19T21:00:00Z";
const A_LAS_19 = "2026-11-19T22:00:00Z";
const casos = [];
const probar = (nombre, ok, detalle) => casos.push([ok, nombre, detalle]);

let p = await correr(undefined, A_LAS_18);
probar("sin el parámetro, la tutoría corre (como siempre en IN5162)",
  p.length === 1 && p[0].flujo === "tests.tutoria" && p[0].args.prueba === false, JSON.stringify(p));
p = await correr("false", A_LAS_18);
probar("con TUTORIA_AUTOMATICA = false no se pide nada", p.length === 0, JSON.stringify(p));
p = await correr("true", A_LAS_18);
probar("con TUTORIA_AUTOMATICA = true corre", p.length === 1 && p[0].semestre === "2099-1", JSON.stringify(p));
p = await correr(undefined, A_LAS_19);
probar("fuera de las 18:00 de Santiago no se pide nada", p.length === 0, JSON.stringify(p));

for (const [ok, nombre, detalle] of casos) console.log(`${ok ? "OK" : "FALLA"}\t${nombre}${ok ? "" : "\t" + detalle}`);
process.exit(casos.every(([ok]) => ok) ? 0 : 1);
