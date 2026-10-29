// Prueba salidaConCorreos() de public/comun.js sin navegador, con un DOM mínimo:
// una línea @@correo de la salida de un trabajo se vuelve un correo dibujado y
// el resto sigue como texto. La corre pruebas/web.py.
class Nodo {
  constructor(t) { this.tag = t; this.hijos = []; this.attrs = {}; this.className = ""; }
  append(...xs) { this.hijos.push(...xs); }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k] ?? null; }
  addEventListener() {}
}
class Texto { constructor(s) { this.texto = s; } }
globalThis.Node = Nodo;
globalThis.document = { createElement: (t) => new Nodo(t), createTextNode: (s) => new Texto(s) };
globalThis.ResizeObserver = class { observe() {} };
const { salidaConCorreos } = await import(new URL("../public/comun.js", import.meta.url));

const todos = (n) => [n, ...(n.hijos || []).flatMap(todos)];
const de = (n, tag) => todos(n).filter((x) => x.tag === tag);
const texto = (n) => todos(n).filter((x) => x instanceof Texto).map((x) => x.texto).join("");
const correo = (c) => `@@correo ${JSON.stringify(c)}`;

let fallas = 0;
const check = (nombre, ok) => { console.log(`${ok ? "OK" : "FALLA"}\t${nombre}`); if (!ok) fallas++; };

const html = '<p>Hola <b>Ana</b></p>\n<blockquote style="color:#555">¿Qué es?</blockquote>';
const caja = salidaConCorreos([
  "Ejemplo CONTROL — Ana → ana@ejemplo.cl",
  correo({ para: "ana@ejemplo.cl", nombre: "Ana", asunto: "Módulo 3", cuerpo: html, html: true, enviado: false }),
  correo({ para: "luis@ejemplo.cl", nombre: "Luis", asunto: "Módulo 3", cuerpo: "Hola <Luis>\nchao", html: false }),
  "✓ listo",
].join("\n"));
const partes = caja.hijos;

check("todo en una sola caja", caja.className === "salida con-correos");
check("texto, correos y texto quedan en ese orden", partes.length === 3
  && partes[0].tag === "pre" && partes[1].className === "correos-trabajo" && partes[2].tag === "pre");
check("dos correos seguidos van juntos", de(partes[1], "details").length === 2);
const [f1, f2] = de(partes[1], "iframe");
check("el HTML va dibujado en un iframe, no como texto", f1?.attrs.srcdoc.includes(html) && !texto(partes[1]).includes("<p>"));
check("el iframe no corre scripts", f1 && !f1.attrs.sandbox.includes("allow-scripts"));
check("el texto plano se escapa y conserva los saltos",
  f2?.attrs.srcdoc.includes("Hola &lt;Luis&gt;\nchao") && f2.attrs.srcdoc.includes("pre-wrap"));
check("la marca no aparece en el texto", !texto({ hijos: partes }).includes("@@correo"));

const roto = salidaConCorreos("@@correo {no es json");
check("una línea marcada pero rota queda como texto",
  !de(roto, "iframe").length && texto(roto).includes("{no es json"));
check("sin correos, la salida es la caja de siempre", salidaConCorreos("✓ hola").tag === "pre");

const vallas = salidaConCorreos(correo({ para: "a@b.cl", asunto: "x", cuerpo: "```html\n<p>hola</p>\n```", html: true }));
check("un cuerpo se muestra tal cual se envió, con vallas ``` incluidas", de(vallas, "iframe")[0].attrs.srcdoc.includes("```html"));
check("el correo no puede pedir nada afuera (imágenes ni CSS remotos)",
  de(vallas, "iframe")[0].attrs.srcdoc.includes("default-src 'none'"));

// Texto recuperado del buzón: cortes cada ~75 caracteres y etiquetas solas en su línea.
const { desenvolver, evaluacionDeTexto, respuestaLegible } = await import(new URL("../public/comun.js", import.meta.url));
const cortado = "Al usar mayores niveles de agregación se puede perder detalle necesario\npara decidir en el corto plazo.\n\n1. Primer punto\n2. Segundo";
check("une las líneas que cortó el correo", desenvolver(cortado).startsWith("Al usar mayores niveles de agregación se puede perder detalle necesario para decidir"));
check("respeta los párrafos y las listas", desenvolver(cortado).includes(".\n\n1. Primer punto\n2. Segundo"));
check("une una línea larga seguida de unas palabras en minúscula",
  desenvolver("mientras que la tasa media de la población que se observó en el periodo completo es solo 8\neventos por unidad.") ===
  "mientras que la tasa media de la población que se observó en el periodo completo es solo 8 eventos por unidad.");
check("no une una frase que terminó", desenvolver("Esto termina acá con un punto final bien puesto y de largo normal.\notra cosa").includes("\notra cosa"));
const ev = evaluacionDeTexto("EVALUACIÓN SEGÚN PAUTA\nA.\nRESPUESTA:\nDice <algo> & más.\nEVALUACIÓN:\n2 / 3 puntos\nNOTA FINAL:\n6,5");
check("las etiquetas van en negrita con su valor al lado", ev.includes("<b>RESPUESTA:</b> Dice &lt;algo&gt; &amp; más.")
  && ev.includes("<b>EVALUACIÓN:</b> 2 / 3 puntos") && ev.includes("<b>NOTA FINAL:</b> 6,5"));
check("el título y el apartado conservan su formato", ev.includes("<strong>EVALUACIÓN SEGÚN PAUTA</strong>") && ev.includes("<u>A.</u>"));
check("se quita el 'El vie, … escribió:' del final de una respuesta",
  respuestaLegible("Mi respuesta.\n\nEl vie, 21 ago 2026 a la(s) 12:01 p.m., <curso@ejemplo.cl> escribió:") === "Mi respuesta.");

process.exit(fallas ? 1 : 0);
