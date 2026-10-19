// Cuándo la sábana está atrasada y se vuelve a armar sola (public/sabana.js).
// La corre pruebas/web.py.
const { estadoSabana } = await import(new URL("../public/sabana.js", import.meta.url));
const a = (ruta, subido) => ({ ruta, subido });
const SABANA = a("exportes/sabana.csv", "2026-10-16T21:00:00.000Z");
const casos = [
  ["al día si nada cambió después de armarla", [a("log_envios.csv", "2026-10-16T20:00:00.000Z"), SABANA], false],
  ["atrasada si el log cambió después (una evaluación, una tutoría)", [a("log_envios.csv", "2026-10-16T22:00:00.000Z"), SABANA], true],
  ["atrasada si cambió el feedback de una tarea", [a("tareas/data/salidas/feedback_T1.csv", "2026-10-17T00:00:00.000Z"), SABANA], true],
  ["subir entregas no la atrasa (la sábana no las lee)", [a("tareas/data/entregas/T1/x.html", "2026-10-17T00:00:00.000Z"), SABANA], false],
  ["sin sábana, hay que armarla", [a("log_envios.csv", "2026-10-16T20:00:00.000Z")], true],
];
let fallas = 0;
for (const [nombre, lista, esperado] of casos) {
  const ok = estadoSabana(lista).atrasada === esperado;
  if (!ok) fallas++;
  console.log(`${ok ? "OK" : "FALLA"}\t${nombre}`);
}
process.exit(fallas ? 1 : 0);
