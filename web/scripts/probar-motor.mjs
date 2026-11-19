// Prueba avisarAlMotor() de src/index.ts sin Worker: saca la función del
// archivo, le quita los tipos con esbuild y le pasa un fetch de mentira. La
// corre pruebas/web.py.
import fs from "node:fs";
import { transformSync } from "esbuild";

const fuente = fs.readFileSync(new URL("../src/index.ts", import.meta.url), "utf-8");
const desde = fuente.indexOf("const REINTENTOS_MOTOR_MS");
const hasta = fuente.indexOf("// Lo que corre solo, todos los días");
if (desde < 0 || hasta < 0) {
  console.log("FALLA\tse encuentra avisarAlMotor en index.ts");
  process.exit(1);
}
const js = transformSync(fuente.slice(desde, hasta), { loader: "ts" }).code;
const casos = [];
const probar = (nombre, ok, detalle) => casos.push([ok, nombre, detalle]);

async function con(respuestas) {
  const pedidos = [];
  const esperas = [];
  globalThis.fetch = async () => {
    const r = respuestas[pedidos.length];
    pedidos.push(1);
    if (r instanceof Error) throw r;
    return { ok: r < 400, status: r, text: async () => "" };
  };
  const avisar = new Function(`${js}\nreturn avisarAlMotor;`)();
  const motivo = await avisar({ MOTOR_URL: "https://motor.test/", TOKEN_WEB: "x" }, "id-1",
    async (ms) => { esperas.push(ms); });
  return { motivo, pedidos: pedidos.length, esperas };
}

let r = await con([200]);
probar("si el motor contesta, un solo aviso y sin motivo", r.motivo === "" && r.pedidos === 1, JSON.stringify(r));
r = await con([500, 200]);
probar("un 500 se reintenta y el trabajo queda encolado", r.motivo === "" && r.pedidos === 2 && r.esperas.length === 1, JSON.stringify(r));
r = await con([new Error("red"), 503, 200]);
probar("un error de red también se reintenta", r.motivo === "" && r.pedidos === 3, JSON.stringify(r));
r = await con([500, 500, 500]);
probar("tres fallos dejan el motivo con los intentos", r.pedidos === 3 && /500.*3 intentos/.test(r.motivo), JSON.stringify(r));
r = await con([401]);
probar("un 401 no se reintenta", r.pedidos === 1 && r.motivo.includes("401"), JSON.stringify(r));

for (const [ok, nombre, detalle] of casos) console.log(`${ok ? "OK" : "FALLA"}\t${nombre}${ok ? "" : "\t" + detalle}`);
process.exit(casos.every(([ok]) => ok) ? 0 : 1);
