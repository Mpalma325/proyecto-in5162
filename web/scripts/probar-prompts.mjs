// Las comprobaciones de public/prompts.js antes de guardar un prompt editado.
// La corre pruebas/web.py.
import fs from "node:fs";

const { PROMPTS, problemasDePrompt } = await import(new URL("../public/prompts.js", import.meta.url));
const evaluar = PROMPTS["tests_semanales/prompts/evaluar_respuesta.md"];
const feedback = PROMPTS["tareas/prompts/correo_feedback.md"];
const casos = [
  ["un prompt de evaluación con sus etiquetas está bien",
    problemasDePrompt(evaluar, "...NOTA FINAL: x\nORIGINALIDAD: y"), 0],
  ["sin «NOTA FINAL:» avisa", problemasDePrompt(evaluar, "...ORIGINALIDAD: y"), 1],
  ["un prompt que pide JSON con «puntaje» y «originalidad» no pide NOTA FINAL",
    problemasDePrompt(evaluar, 'Devuelve JSON: {"preguntas": [{"puntaje": 2}], "originalidad": "Media"}'), 0],
  ["un prompt JSON sin «originalidad» avisa",
    problemasDePrompt(evaluar, 'Devuelve JSON: {"preguntas": [{"puntaje": 2}]}'), 1],
  ["el prompt de la plantilla (JSON) pasa", problemasDePrompt(evaluar, fs.readFileSync(
    new URL("../../semestres/_template/tests_semanales/prompts/evaluar_respuesta.md", import.meta.url), "utf8")), 0],
  ["un correo de tareas con sus variables está bien",
    problemasDePrompt(feedback, "Hola {nombre}, tu nota en {tarea} es {nota}. {{llaves}}"), 0],
  ["una variable que no existe avisa", problemasDePrompt(feedback, "Hola {Nombre}"), 1],
  ["una llave suelta avisa", problemasDePrompt(feedback, "Hola {nombre}, mira esto: {"), 1],
  ["en los correos de tests las llaves no se revisan (no usan str.format)",
    problemasDePrompt(PROMPTS["tests_semanales/prompts/correo_pregunta.md"], "<p>{ suelta</p>"), 0],
];
let fallas = 0;
for (const [nombre, problemas, esperados] of casos) {
  const ok = problemas.length === esperados;
  if (!ok) fallas++;
  console.log(`${ok ? "OK" : "FALLA"}\t${nombre}${ok ? "" : ` → ${JSON.stringify(problemas)}`}`);
}
process.exit(fallas ? 1 : 0);
