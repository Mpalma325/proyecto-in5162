// Trabajos programados más allá de lo que acepta la cola (src/index.ts): un
// test se confirma con su envío y su cierre a meses, y Cloud Tasks solo acepta
// 30 días. Saca de index.ts desde PROGRAMAR_HASTA_DIAS hasta los reintentos, le
// quita los tipos con esbuild y lo corre sobre una D1 de mentira. La corre
// pruebas/web.py.
import fs from "node:fs";
import { transformSync } from "esbuild";

const fuente = fs.readFileSync(new URL("../src/index.ts", import.meta.url), "utf-8");
const desde = fuente.indexOf("const PROGRAMAR_HASTA_DIAS");
const hasta = fuente.indexOf("// Esperas antes de cada reintento");
if (desde < 0 || hasta < 0) {
  console.log("FALLA\tse encuentran los trabajos programados en index.ts");
  process.exit(1);
}
const js = transformSync(fuente.slice(desde, hasta), { loader: "ts" }).code;
const W = new Function("error", "ahora", "avisarAlMotor",
  `${js}\nreturn { horaProgramada, fueraDeLaVentana, porEncolar, crearTrabajo, encolarLosQueEsperan, VENTANA_COLA_DIAS, PROGRAMAR_HASTA_DIAS };`)(
  (estado, mensaje) => ({ estado, mensaje }), () => new Date().toISOString(),
  async () => { throw new Error("la prueba siempre pasa su propio aviso"); });

/** Lo justo de D1 para estas consultas: INSERT, el SELECT del cron y los UPDATE condicionados. */
function d1() {
  const filas = new Map();
  const prepare = (sql) => ({ bind: (...v) => ({
    async run() {
      if (sql.startsWith("INSERT INTO trabajos")) {
        const [id, semestre, flujo, argumentos, prueba, pedido_por] = v;
        filas.set(id, { id, semestre, flujo, argumentos, prueba, estado: "pendiente", pedido_por, salida: "" });
        return { meta: { changes: 1 } };
      }
      if (sql.startsWith("UPDATE trabajos SET argumentos")) {
        const [despues, , id, antes] = v;
        const f = filas.get(id);
        if (!f || f.estado !== "pendiente" || f.argumentos !== antes) return { meta: { changes: 0 } };
        f.argumentos = despues;
        return { meta: { changes: 1 } };
      }
      if (sql.startsWith("UPDATE trabajos SET estado = 'fallido'")) {
        const [salida, , id] = v;
        Object.assign(filas.get(id), { estado: "fallido", salida });
        return { meta: { changes: 1 } };
      }
      throw new Error(`SQL no esperado: ${sql}`);
    },
    async all() {
      if (!sql.includes("instr(argumentos, ?)")) throw new Error(`SQL no esperado: ${sql}`);
      const results = [...filas.values()].filter((f) => f.estado === "pendiente" && f.argumentos.includes(v[0]));
      return { results: results.map(({ id, argumentos }) => ({ id, argumentos })) };
    },
  }) });
  return { filas, DB: { prepare } };
}

let fallas = 0;
const check = (nombre, ok, detalle = "") => {
  if (!ok) fallas++;
  console.log(`${ok ? "OK" : "FALLA"}\t${nombre}${ok || !detalle ? "" : ` → ${detalle}`}`);
};

const DIA = 86_400_000;
const hoy = Date.parse("2026-08-03T12:00:00Z");
const en = (dias) => new Date(hoy + dias * DIA).toISOString();

// ---------------------------------------------------------------- la hora que acepta el Worker
check("acepta un envío a 90 días (antes rechazaba todo lo que pasara de 30)",
  typeof W.horaProgramada(en(90), hoy) === "string", JSON.stringify(W.horaProgramada(en(90), hoy)));
check(`rechaza más de ${W.PROGRAMAR_HASTA_DIAS} días`, W.horaProgramada(en(W.PROGRAMAR_HASTA_DIAS + 1), hoy).estado === 400);
check("rechaza una hora que ya pasó", W.horaProgramada(en(-1), hoy).estado === 400);
check("guarda en UTC", W.horaProgramada("2026-09-07T10:15:00-03:00", hoy) === "2026-09-07T13:15:00.000Z");

// ---------------------------------------------------------------- crear: dentro o fuera de la ventana
const { filas, DB } = d1();
const env = { DB };
const avisos = [];
const avisar = async (_env, id) => { avisos.push(id); return ""; };
const cerca = await W.crearTrabajo(env, "2027-1", "tests.enviar", { instancia: 1, prueba: false, a_las: en(10) },
  "profe@x.cl", avisar, hoy);
check("un trabajo a 10 días se le avisa al motor al crearlo", avisos.includes(cerca)
  && !JSON.parse(filas.get(cerca).argumentos)._en_espera, filas.get(cerca).argumentos);
const lejos = await W.crearTrabajo(env, "2027-1", "tests.evaluar", { instancia: 1, prueba: false, a_las: en(80) },
  "profe@x.cl", avisar, hoy);
check("uno a 80 días queda pendiente en D1, sin avisarle al motor",
  !avisos.includes(lejos) && filas.get(lejos).estado === "pendiente", JSON.stringify(avisos));
check("y marcado como en espera, con su a_las intacto",
  JSON.parse(filas.get(lejos).argumentos)._en_espera === true && JSON.parse(filas.get(lejos).argumentos).a_las === en(80));
const ahora = await W.crearTrabajo(env, "2027-1", "tests.resumen", { instancia: 1, _en_espera: true }, "x", avisar, hoy);
check("sin a_las se avisa enseguida, y la marca no la puede poner la página",
  avisos.includes(ahora) && !("_en_espera" in JSON.parse(filas.get(ahora).argumentos)));

// ---------------------------------------------------------------- el cron
const otro = await W.crearTrabajo(env, "2027-1", "tests.enviar", { instancia: 2, prueba: false, a_las: en(120) },
  "x", avisar, hoy);
const cancelado = await W.crearTrabajo(env, "2027-1", "tests.enviar", { instancia: 3, prueba: false, a_las: en(31) },
  "x", avisar, hoy);
filas.get(cancelado).estado = "cancelado"; // «Volver a borrador» antes de encolarlo
avisos.length = 0;
let r = await W.encolarLosQueEsperan(env, hoy + 10 * DIA, avisar);
check("el cron no encola nada que todavía no entra en la ventana", r.length === 0 && avisos.length === 0, JSON.stringify(r));
r = await W.encolarLosQueEsperan(env, hoy + 52 * DIA, avisar);
check("cuando el de 80 días queda a 28, el cron le avisa al motor", JSON.stringify(r) === JSON.stringify([lejos])
  && JSON.stringify(avisos) === JSON.stringify([lejos]), JSON.stringify(r));
check("y le quita la marca, sin tocar el resto de sus argumentos",
  JSON.stringify(JSON.parse(filas.get(lejos).argumentos)) === JSON.stringify({ instancia: 1, prueba: false, a_las: en(80) }),
  filas.get(lejos).argumentos);
check("el cancelado no se encola ni se revive", !avisos.includes(cancelado) && filas.get(cancelado).estado === "cancelado");
r = await W.encolarLosQueEsperan(env, hoy + 52 * DIA, avisar);
check("correrlo dos veces (las dos horas del cron) no avisa dos veces", r.length === 0 && avisos.length === 1,
  JSON.stringify(avisos));
check("el de 120 días sigue esperando", JSON.parse(filas.get(otro).argumentos)._en_espera === true);
const pw = W.porEncolar([{ id: "a", argumentos: JSON.stringify({ a_las: en(5), _en_espera: true }) },
  { id: "b", argumentos: "no es json" }, { id: "c", argumentos: JSON.stringify({ a_las: en(5) }) }], hoy);
check("porEncolar ignora lo que no está en espera o no se puede leer", pw.length === 1 && pw[0].id === "a", JSON.stringify(pw));
const tarde = await W.encolarLosQueEsperan(env, hoy + 100 * DIA, async () => "el motor respondió 500");
check("si el motor no contesta, queda fallido con el motivo (no pendiente para siempre)",
  JSON.stringify(tarde) === JSON.stringify([otro]) && filas.get(otro).estado === "fallido"
  && /500/.test(filas.get(otro).salida), filas.get(otro).salida);

// ---------------------------------------------------------------- la página
const { programadoPara } = await import(new URL("../public/comun.js", import.meta.url));
check("la página muestra el trabajo en espera como programado, igual que cualquier otro",
  programadoPara({ estado: "pendiente", argumentos: { a_las: en(80), _en_espera: true } }, hoy)?.getTime()
    === hoy + 80 * DIA);

process.exit(fallas ? 1 : 0);
