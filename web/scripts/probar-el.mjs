// Prueba el() de public/comun.js sin navegador, con un DOM mínimo. Una lista
// dentro de otra (las semanas de la ficha de un alumno) se mostraba como
// "[object HTMLParagraphElement],[object HTMLDivElement]". La corre pruebas/web.py.
class Nodo { constructor(t) { this.tag = t; this.hijos = []; } append(...xs) { this.hijos.push(...xs); } setAttribute() {} addEventListener() {} }
class Texto { constructor(s) { this.texto = s; } }
globalThis.Node = Nodo;
globalThis.document = { createElement: (t) => new Nodo(t), createTextNode: (s) => new Texto(s) };
const { el } = await import(new URL("../public/comun.js", import.meta.url));

const div = el("div", {}, [[el("p"), el("div")], [el("p"), null], el("span")], "texto");
const textos = div.hijos.filter((h) => h instanceof Texto).map((h) => h.texto);
const ok = div.hijos.length === 5 && textos.length === 1 && textos[0] === "texto";
console.log(`${ok ? "OK" : "FALLA"}\tlistas anidadas se aplanan, sin convertir nodos a texto`);
process.exit(ok ? 0 : 1);
