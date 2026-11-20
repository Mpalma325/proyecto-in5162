// Los prompts del semestre: para qué sirve cada uno y qué variables les
// reemplaza el código. Los correos de Tareas pasan por str.format de Python
// (`formato`): ahí una llave suelta o una variable que no existe hace fallar
// el envío. `obligatorias` son etiquetas que el sistema busca en lo que
// devuelve la IA. Sin pantalla, para probarlo sin navegador
// (web/scripts/probar-prompts.mjs).

import { pideJson } from "./correccion.js";

export const PROMPTS = {
  "tests_semanales/prompts/correo_pregunta.md": {
    titulo: "Correo con la pregunta de la semana",
    uso: "{ESCALA} es el rango de la escala de notas del semestre, por ejemplo «4,0 a 7,0».",
    variables: ["{NOMBRE}", "{TEMA}", "{FECHA_ENTREGA}", "{BLOQUE_PREGUNTAS}", "{SEMANA}", "{TITULO}", "{ESCALA}"] },
  "tests_semanales/prompts/evaluar_respuesta.md": {
    titulo: "Cómo corrige la IA cada respuesta",
    uso: "Antes de cambiarlo, conviene probarlo en Configuración › La IA › Probar criterio. Puede pedir la "
      + "salida en JSON, con «puntaje» por pregunta y «originalidad» (la nota la calcula la escala del semestre), "
      + "o en HTML con NOTA FINAL y ORIGINALIDAD, como los semestres anteriores.",
    variables: ["{{PREGUNTAS}}", "{{PAUTAS}}"],
    // El formato lo decide el texto (correccion.pide_json): cada uno busca sus etiquetas.
    obligatorias: (texto) => (pideJson(texto) ? ['"puntaje"', '"originalidad"'] : ["NOTA FINAL:", "ORIGINALIDAD:"]) },
  "tests_semanales/prompts/correo_correccion.md": {
    titulo: "Correo con la corrección",
    uso: "{EVALUACION} es lo que escribe la IA; lo demás sale igual para todos.",
    variables: ["{NOMBRE}", "{EVALUACION}"] },
  "tests_semanales/prompts/tutoria.md": {
    titulo: "Cómo responde la IA las dudas de los alumnos",
    variables: ["{NOMBRE}"] },
  "tests_semanales/prompts/resumen_respuestas.md": {
    titulo: "Resumen de la semana", variables: [] },
  "tests_semanales/prompts/correo_duplicado.md": {
    titulo: "Correo a quien responde dos veces",
    variables: ["{NOMBRE}"] },
  "tareas/prompts/generar_preguntas.md": {
    titulo: "Cómo genera la IA la pregunta de cada alumno",
    variables: [] },
  "tareas/prompts/correo_pregunta.md": {
    titulo: "Correo con la pregunta de la tarea", formato: true,
    variables: ["{nombre}", "{tarea}", "{pregunta_tarea}", "{pregunta}", "{plazo}", "{minutos}"] },
  "tareas/prompts/corregir_respuesta.md": {
    titulo: "Cómo corrige la IA la respuesta de la tarea",
    uso: "Tiene que pedir la respuesta en JSON, con «nota» y «comentario».",
    variables: ["{NOTA_MIN}", "{NOTA_MAX}", "{NOTA_INT_ALTA}", "{NOTA_INT_MEDIA}"] },
  "tareas/prompts/correo_feedback.md": {
    titulo: "Correo con la corrección de la tarea",
    formato: true, variables: ["{nombre}", "{tarea}", "{pregunta}", "{respuesta}", "{comentario}", "{nota}", "{ajuste}"] },
  "tareas/prompts/correo_segunda_oportunidad.md": {
    titulo: "Correo de la segunda oportunidad",
    formato: true, variables: ["{nombre}", "{tarea}", "{pregunta_tarea}", "{pregunta}"] },
};

/** Lo que haría fallar o dejaría sin nota a este prompt: lista de frases, vacía si está bien. */
export function problemasDePrompt(info, texto) {
  const problemas = [];
  const obligatorias = typeof info?.obligatorias === "function" ? info.obligatorias(texto) : info?.obligatorias || [];
  for (const etiqueta of obligatorias) {
    if (!texto.includes(etiqueta)) {
      problemas.push(`Falta «${etiqueta}»: el sistema lo busca en lo que responde la IA para guardar la nota.`);
    }
  }
  if (info?.formato) {
    // Como str.format: {{ y }} son llaves literales; {nombre} tiene que ser una variable conocida.
    const sinDobles = texto.replaceAll("{{", "").replaceAll("}}", "");
    const validas = new Set(info.variables.map((v) => v.slice(1, -1)));
    const usadas = [...sinDobles.matchAll(/\{([^{}]*)\}/g)].map((m) => m[1]);
    const desconocidas = [...new Set(usadas.filter((v) => !validas.has(v)))];
    if (desconocidas.length) {
      problemas.push(`Variables que no existen: ${desconocidas.map((v) => `{${v}}`).join(", ")}. El envío fallaría.`);
    }
    if (/[{}]/.test(sinDobles.replace(/\{[^{}]*\}/g, ""))) {
      problemas.push("Hay una llave { o } suelta. Para escribir una llave en el correo, ponla doble: {{ o }}.");
    }
  }
  return problemas;
}
