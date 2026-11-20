// Copia agregaciones.py a public/py/ para que la página lo cargue en Pyodide.
//
// Es la misma lógica que usan los scripts, no una traducción: si alguien cambia
// una métrica en Python, la página la calcula igual en el próximo despliegue.
import { mkdirSync, copyFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const aqui = dirname(fileURLToPath(import.meta.url));
const origen = join(aqui, "..", "..", "modulos", "datos", "agregaciones.py");
const destino = join(aqui, "..", "public", "py", "agregaciones.py");
mkdirSync(dirname(destino), { recursive: true });
copyFileSync(origen, destino);
console.log(`agregaciones.py -> ${destino}`);
