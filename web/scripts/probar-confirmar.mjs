// confirmar() de public/comun.js sin navegador, con un DOM mínimo: arma un
// <dialog> con el texto y dos botones, parte con el foco en «Cancelar» y da
// true solo si se eligió la acción. También revisa que ninguna página siga
// usando el confirm del navegador. La corre pruebas/web.py.
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

class Nodo {
  constructor(tag) {
    this.tag = tag; this.hijos = []; this.attrs = {}; this.oyentes = {}; this.padre = null; this.className = "";
    if (tag === "dialog") this.returnValue = "";
  }
  append(...xs) { for (const x of xs) { if (x instanceof Nodo) x.padre = this; this.hijos.push(x); } }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(tipo, f) { (this.oyentes[tipo] ||= []).push(f); }
  remove() { if (this.padre) this.padre.hijos = this.padre.hijos.filter((h) => h !== this); this.padre = null; }
  focus() { globalThis.document.activeElement = this; }
  get textContent() { return this.hijos.map((h) => (h instanceof Nodo ? h.textContent : h.texto)).join(""); }
  buscar(f) { return [this, ...this.hijos.filter((h) => h instanceof Nodo).flatMap((h) => h.buscar(f))].filter(f); }
  // Lo de <dialog>: un botón de un <form method="dialog"> lo cierra con su value; Esc, sin valor.
  showModal() { this.modal = true; }
  close(valor) {
    if (valor !== undefined) this.returnValue = valor;
    this.modal = false;
    (this.oyentes.close || []).forEach((f) => f());
  }
}
class Texto { constructor(s) { this.texto = s; } }
globalThis.Node = Nodo;
const body = new Nodo("body");
globalThis.document = { body, createElement: (t) => new Nodo(t), createTextNode: (s) => new Texto(s) };

const { confirmar } = await import(new URL("../public/comun.js", import.meta.url));

let fallas = 0;
const check = (nombre, ok, detalle = "") => {
  if (!ok) fallas++;
  console.log(`${ok ? "OK" : "FALLA"}\t${nombre}${ok || !detalle ? "" : ` → ${detalle}`}`);
};
const dialogos = () => body.hijos.filter((h) => h.tag === "dialog");

const texto = "Vas a mandar la pregunta de la semana 4 a todos los alumnos que no la tienen.\n\n¿Confirmas?";
const promesa = confirmar(texto, "Enviar preguntas", "real");
check("confirmar devuelve una promesa", promesa instanceof Promise);
const [d] = dialogos();
check("abre un <dialog> modal en la página", dialogos().length === 1 && d.modal === true);
const botones = d ? d.buscar((n) => n.tag === "button") : [];
const parrafo = d?.buscar((n) => n.tag === "p")[0];
check("con el mismo texto que llevaba el confirm", parrafo?.textContent === texto, parrafo?.textContent);
check("el diálogo se describe con ese texto (lector de pantalla)",
  Boolean(parrafo?.attrs.id) && d.attrs["aria-describedby"] === parrafo.attrs.id);
check("dos botones: «Cancelar» y la acción", botones.map((b) => b.textContent).join("|") === "Cancelar|Enviar preguntas",
  botones.map((b) => b.textContent).join("|"));
check("el foco parte en «Cancelar»", globalThis.document.activeElement === botones[0]);
check("la acción va pintada como primaria y real", botones[1]?.className === "primario real", botones[1]?.className);
check("los dos botones cierran el diálogo (form method=dialog)",
  d?.buscar((n) => n.tag === "form")[0]?.attrs.method === "dialog" && botones.every((b) => b.attrs.type === "submit"));
d.close(botones[1].attrs.value);
check("elegir la acción da true", (await promesa) === true);
check("y el diálogo se quita de la página", dialogos().length === 0);

const conEsc = confirmar("¿Descartar los cambios?", "Descartar");
dialogos()[0].close(); // Esc: se cierra sin valor
check("Esc da false", (await conEsc) === false);
const conCancelar = confirmar("¿Descartar los cambios?");
const [d2] = dialogos();
const [cancelar, aceptar] = d2.buscar((n) => n.tag === "button");
check("sin acción ni tono, el botón dice «Aceptar» y es primario", aceptar.textContent === "Aceptar"
  && aceptar.className === "primario", `${aceptar.textContent} ${aceptar.className}`);
d2.close(cancelar.attrs.value);
check("«Cancelar» da false", (await conCancelar) === false);

// Ninguna página llama al confirm del navegador, y las que usan confirmar lo importan.
const carpeta = new URL("../public/", import.meta.url);
const paginas = fs.readdirSync(carpeta).filter((f) => f.endsWith(".js"));
const conConfirm = [];
const sinImportar = [];
for (const f of paginas) {
  const fuente = fs.readFileSync(new URL(f, carpeta), "utf8");
  const sinComentarios = fuente.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
  if (/(^|[^\w.$])confirm\s*\(|window\.confirm\b/m.test(sinComentarios)) conConfirm.push(f);
  const importa = fuente.match(/import\s*\{([^}]*)\}\s*from\s*"\.\/comun\.js"/);
  if (f !== "comun.js" && /\bconfirmar\(/.test(sinComentarios) && !/\bconfirmar\b/.test(importa?.[1] || "")) sinImportar.push(f);
}
check("ninguna página usa el confirm del navegador", !conConfirm.length, conConfirm.join(", "));
check("las páginas que piden confirmar importan confirmar", !sinImportar.length, sinImportar.join(", "));
// Un await dentro de una función que no es async no se ve hasta que la página carga: se revisa la sintaxis.
const rotas = paginas.filter((f) => spawnSync(process.execPath, ["--check", fileURLToPath(new URL(f, carpeta))],
  { encoding: "utf8" }).status !== 0);
check(`las ${paginas.length} páginas se pueden leer (sin errores de sintaxis)`, !rotas.length, rotas.join(", "));

process.exit(fallas ? 1 : 0);
