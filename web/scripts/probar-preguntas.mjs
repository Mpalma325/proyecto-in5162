// Prueba la lógica del editor de preguntas por semana (public/preguntas.js) sin
// navegador. La corre pruebas/web.py, que le pasa un preguntas.csv y lo que se
// espera, calculado con el Python que de verdad envía los correos:
//
//   node probar-preguntas.mjs preguntas.csv esperado.json
//
// esperado.json: { plantilla, semanas: [n...], iguales: { n: [bool...] },
//                  sin_tratamiento: [n...], correos: { n: { control, tratamiento } } }
import fs from "node:fs";

const { leerCsv, escribirCsv } = await import(new URL("../public/csv.js", import.meta.url));
const P = await import(new URL("../public/preguntas.js", import.meta.url));

const [rutaCsv, rutaEsperado] = process.argv.slice(2);
const texto = fs.readFileSync(rutaCsv, "utf8");
const esperado = JSON.parse(fs.readFileSync(rutaEsperado, "utf8"));
const datos = leerCsv(texto);
let fallas = 0;
const check = (nombre, ok, detalle = "") => {
  if (!ok) fallas++;
  console.log(`${ok ? "OK" : "FALLA"}\t${nombre}${ok || !detalle ? "" : ` → ${detalle}`}`);
};
const lineasDistintas = (a, b) => {
  const [x, y] = [a.split("\n"), b.split("\n")];
  return Array.from({ length: Math.max(x.length, y.length) }, (_, i) => i).filter((i) => x[i] !== y[i]);
};

check("tiene las columnas del editor", P.columnasFaltantes(datos).length === 0, P.columnasFaltantes(datos).join(", "));
const numeros = P.semanasDe(datos).map((s) => s.numero);
check("lista las semanas en orden, sin las filas en blanco",
  JSON.stringify(numeros) === JSON.stringify(esperado.semanas), JSON.stringify(numeros));

for (const n of esperado.semanas) {
  const s = P.leerSemana(datos, n);
  const iguales = s.preguntas.map((p) => p.igual);
  check(`semana ${n}: reconoce qué preguntas son iguales para los dos grupos`,
    JSON.stringify(iguales) === JSON.stringify(esperado.iguales[n]), JSON.stringify(iguales));

  // Guardar sin tocar nada deja el archivo igual. Salvo una semana con
  // Tratamiento vacío: ahí se escribe explícito lo que preguntas.py ya le manda.
  const otra = escribirCsv(P.escribirSemana(datos, n, s));
  const cambian = lineasDistintas(texto, otra);
  if (esperado.sin_tratamiento.includes(n)) {
    check(`semana ${n} (Tratamiento vacío): solo cambia su propia fila`, cambian.length === 1, JSON.stringify(cambian));
    const releida = P.leerSemana(leerCsv(otra), n);
    check(`semana ${n} (Tratamiento vacío): después de guardar, Tratamiento recibe lo mismo`,
      JSON.stringify(releida) === JSON.stringify(s));
  } else {
    check(`semana ${n}: guardar sin cambios deja el archivo igual, byte a byte`, otra === texto, JSON.stringify(cambian));
  }

  for (const grupo of ["control", "tratamiento"]) {
    const { html } = P.correoDe(esperado.plantilla, s, grupo, "Ana");
    check(`semana ${n}: la vista previa de ${grupo} es el correo que arma enviar.py`,
      html === esperado.correos[n][grupo], `${JSON.stringify(html.slice(0, 160))}…`);
  }
}

// Editar una semana cambia esa fila y nada más.
const n = esperado.semanas.find((x) => !esperado.sin_tratamiento.includes(x));
const s = P.leerSemana(datos, n);
s.fecha = "lunes 19/10, 10:15";
s.preguntas[0].control.texto += " ¿Y si el precio sube, \"mucho\"?";
const editado = escribirCsv(P.escribirSemana(datos, n, s));
// Por filas del CSV, no por líneas: una celda con salto de línea ocupa dos.
const filasCambiadas = leerCsv(editado).filas
  .map((f, i) => (JSON.stringify(f) === JSON.stringify(datos.filas[i]) ? null : i)).filter((i) => i !== null);
check("editar una semana cambia solo su fila",
  JSON.stringify(filasCambiadas) === JSON.stringify([datos.filas.findIndex((f) => f[0] === String(n))]),
  JSON.stringify(filasCambiadas));
const releida = P.leerSemana(leerCsv(editado), n);
check("lo editado se lee de vuelta igual (comillas y comas incluidas)",
  releida.fecha === s.fecha && releida.preguntas[0].control.texto === s.preguntas[0].control.texto);

// Quitar la primera pregunta corre las demás un lugar.
const sinPrimera = { ...P.leerSemana(datos, n) };
sinPrimera.preguntas = sinPrimera.preguntas.slice(1);
const corrida = P.leerSemana(leerCsv(escribirCsv(P.escribirSemana(datos, n, sinPrimera))), n);
check("quitar la pregunta 1 deja la 2 como 1", corrida.preguntas.length === sinPrimera.preguntas.length
  && JSON.stringify(corrida.preguntas[0]) === JSON.stringify(sinPrimera.preguntas[0]));

// Agregar una semana: la siguiente a la última, antes de las filas en blanco.
const [conNueva, nueva] = P.agregarSemana(datos);
check("una semana nueva es la siguiente a la última", nueva === Math.max(...esperado.semanas) + 1, String(nueva));
const idx = conNueva.filas.findIndex((f) => f[0] === String(nueva));
check("y queda justo después de la última semana", idx === datos.filas.findIndex((f) => f[0] === String(nueva - 1)) + 1,
  String(idx));
const vacia = P.leerSemana(conNueva, nueva);
check("una semana nueva avisa que no tiene preguntas", P.avisosDe(vacia, true).includes("sin preguntas"));
vacia.tema = "Nueva";
vacia.preguntas = [{ control: { texto: "¿Qué?", pauta: "Esto." }, tratamiento: { texto: "¿Qué?", pauta: "Esto." }, igual: true }];
const guardadaNueva = P.leerSemana(leerCsv(escribirCsv(P.escribirSemana(conNueva, nueva, vacia))), nueva);
check("y se guarda con su pregunta en los dos grupos", guardadaNueva.preguntas.length === 1 && guardadaNueva.preguntas[0].igual
  && P.avisosDe(guardadaNueva, true).join() === "sin fecha", P.avisosDe(guardadaNueva, true).join());

// La fecha de entrega es texto libre: se reconoce lo que se ha usado en el curso.
const hoy = new Date(2026, 9, 16);
const comoTexto = (d) => (d ? `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()} ${d.getHours()}:${d.getMinutes()}` : null);
for (const [texto, esperado] of [
  ["lunes 19/10/2026, 10:15", "2026-10-19 10:15"],
  [" Viernes 05/06/2026", "2026-6-5 23:59"],
  ["lunes 13/06 10:15", "2026-6-13 10:15"],
  ["2026-03-15", "2026-3-15 23:59"],
  ["19/10/26", "2026-10-19 23:59"],
  ["31/02/2026", null],
  ["el próximo lunes", null],
  ["", null],
]) {
  const obtenido = comoTexto(P.fechaEntrega(texto, hoy));
  check(`fecha de entrega «${texto}» → ${esperado ?? "no se reconoce"}`, obtenido === esperado, String(obtenido));
}

// El día nombrado tiene que ser el de la fecha: si no, la fecha se copió mal.
for (const [texto, avisa] of [
  ["lunes 13/06 10:15", true],
  ["lunes 22/06 10:15", false],
  [" Viernes 05/06/2026", false],
  ["Sábado 05/06/2026", true],
  ["miercoles 21/10/2026", false],
  ["19/10/2026", false],
  ["el próximo lunes", false],
]) {
  const aviso = P.diaQueNoCalza(texto, hoy);
  check(`«${texto}» ${avisa ? "avisa" : "no avisa"} por el día de la semana`, Boolean(aviso) === avisa, String(aviso));
}
check("el aviso dice qué día es en realidad",
  P.diaQueNoCalza("lunes 13/06 10:15", hoy) === "La fecha dice lunes, pero el 13/06/2026 es sábado.",
  P.diaQueNoCalza("lunes 13/06 10:15", hoy));

process.exit(fallas ? 1 : 0);
