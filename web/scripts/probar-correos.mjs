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

process.exit(fallas ? 1 : 0);
