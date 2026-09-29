// Datos y Configuración: la misma página de Streamlit, sobre los archivos del
// semestre en R2 y los parámetros guardados en D1.
//
// Lo que se edita acá es lo mismo que se editaba en el PC: la lista de alumnos,
// las preguntas, los prompts y las entregas. El resto de los archivos solo los
// escriben los trabajos, y el Worker rechaza cualquier otra ruta.

import { api, caja, el, navegacion, tareasConocidas } from "./comun.js";
import { escribirCsv, leerCsv } from "./csv.js";

document.getElementById("nav").replaceWith(navegacion());
const app = document.getElementById("app");

const RUTAS = {
  alumnos: "alumnos.csv",
  preguntas: "tests_semanales/data/preguntas.csv",
  alumnosTareas: "tareas/data/alumnos.csv",
  entregas: "tareas/data/entregas/",
  salidas: "tareas/data/salidas/",
};

// Los valores que usa config.py cuando nadie los cambió desde la página.
const DEFECTO = {
  MODELO: "gpt-5.4-mini", TEMPERATURA: "0.2", MAX_TOKENS: "3000",
  NOTA_MIN: "4.0", NOTA_MAX: "7.0", TAREA_DEFAULT: "T1",
  GRUPO_CONTROL_TRATAMIENTO: "true", GRUPO_SEED: "19",
};
const MODELOS_CONOCIDOS = ["gpt-5.4-mini", "gpt-5.5", "gpt-5.4", "gpt-5.4-nano", "gpt-5-mini",
  "gpt-4o-mini", "gpt-4o"];

let semestres = [];
let semestre = null; // el activo
let archivos = []; // [{ ruta, bytes, etag }] del semestre activo
let parametros = {}; // clave -> { valor, actualizado, por }
let sinGuardar = false; // hay un editor con cambios que no se guardaron

const [pestanaInicial, subInicial] = location.hash.slice(1).split("/");
let pestana = pestanaInicial === "parametros" ? "parametros" : "datos";
let sub = subInicial || "alumnos";

addEventListener("beforeunload", (e) => { if (sinGuardar) e.preventDefault(); });

function descartarCambios() {
  if (!sinGuardar) return true;
  if (!confirm("Hay cambios sin guardar. ¿Descartarlos?")) return false;
  sinGuardar = false;
  return true;
}

// ---------------------------------------------------------------- archivos

const rutaUrl = (ruta) => ruta.split("/").map(encodeURIComponent).join("/");
const urlArchivo = (ruta) => `/api/archivo/${encodeURIComponent(semestre)}/${rutaUrl(ruta)}`;
const existe = (ruta) => archivos.some((a) => a.ruta === ruta);
const nombre = (ruta) => ruta.split("/").pop();

async function leerTexto(ruta) {
  const r = await fetch(urlArchivo(ruta), { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.text();
}

/**
 * Guarda un archivo sin pisar cambios ajenos: manda el etag de la versión que
 * se cargó. Si alguien lo cambió mientras tanto, el sitio responde 409 y la
 * edición no se pierde: queda en pantalla para copiarla y recargar.
 */
async function guardarArchivo(ruta, cuerpo, tipo) {
  const previo = archivos.find((a) => a.ruta === ruta);
  const condicion = previo ? { "if-match": previo.etag } : { "if-none-match": "*" };
  await api(urlArchivo(ruta), { method: "PUT", headers: { "content-type": tipo, ...condicion }, body: cuerpo });
  archivos = await api(`/api/archivos/${encodeURIComponent(semestre)}`);
}

function bajarComo(nombreArchivo, texto) {
  const a = el("a", { href: URL.createObjectURL(new Blob([texto], { type: "text/csv" })),
    download: nombreArchivo });
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/** Un botón "Subir ..." que entrega el texto del archivo elegido. */
function botonSubir(texto, aceptar, alElegir) {
  const input = el("input", { type: "file", accept: aceptar });
  input.addEventListener("change", async () => {
    if (input.files[0]) alElegir(await input.files[0].text(), input.files[0].name);
    input.value = "";
  });
  return el("label", { class: "descarga" }, texto, input);
}

// ---------------------------------------------------------------- recalcular la reportería

// La reportería se calcula en el motor con reportes.panel(). Si cambia la lista
// de alumnos o las preguntas, se pide un recálculo: no manda correos ni llama
// al modelo, y tarda unos segundos.
async function recalcularReporteria(destino) {
  destino.replaceChildren(caja("info", "Actualizando la reportería con los cambios…"));
  try {
    const { id } = await api("/api/trabajos", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ semestre, flujo: "datos.panel", argumentos: {} }),
    });
    for (let i = 0; i < 120; i++) {
      await new Promise((ok) => setTimeout(ok, 1500));
      const t = await api(`/api/trabajos/${id}`);
      if (t.estado === "terminado") {
        destino.replaceChildren(caja("exito", "Guardado. La reportería ya muestra los cambios."));
        return;
      }
      if (t.estado === "fallido") {
        destino.replaceChildren(caja("aviso",
          "Guardado, pero no pude actualizar la reportería. Se actualizará con el próximo trabajo."));
        return;
      }
    }
    destino.replaceChildren(caja("info", "Guardado. La reportería se sigue actualizando en el motor."));
  } catch (e) {
    destino.replaceChildren(caja("aviso", `Guardado, pero no pude pedir el recálculo: ${e.message}`));
  }
}

// ---------------------------------------------------------------- editor de CSV

/**
 * Una grilla editable, como st.data_editor: se edita cada celda, se agregan y
 * quitan filas, y se guarda el archivo completo. Guardar sin tocar nada deja
 * el archivo igual, byte a byte (csv.js respeta su formato).
 */
function editorCsv(ruta, { alGuardar } = {}) {
  const contenedor = el("div", {}, el("p", { class: "cargando" }, "Cargando…"));

  function montar(datos, desdeArchivo) {
    const mensaje = el("div");
    const guardar = el("button", { class: "primario", type: "button", disabled: !desdeArchivo },
      "Guardar cambios");
    const pie = el("p", { class: "nota-pie" });
    const cuerpo = el("tbody");

    const marcarCambio = () => {
      sinGuardar = true;
      guardar.disabled = false;
      mensaje.replaceChildren();
    };
    const actualizarPie = () => {
      pie.textContent = `${datos.filas.length} filas · ${datos.columnas.length} columnas · ${nombre(ruta)}`;
    };

    const dibujarFilas = () => {
      cuerpo.replaceChildren(...datos.filas.map((fila, i) => el("tr", {},
        el("td", { class: "num" }, i + 1),
        fila.map((valor, j) => {
          const celda = el("div", { class: "celda", contenteditable: "plaintext-only" }, valor);
          celda.addEventListener("input", () => {
            datos.filas[i][j] = celda.innerText.replace(/\n$/, "");
            celda.parentElement.classList.add("cambiado");
            marcarCambio();
          });
          return el("td", {}, celda);
        }),
        el("td", {}, el("button", {
          class: "quitar", type: "button", title: "Quitar fila", "aria-label": `Quitar fila ${i + 1}`,
          onclick: () => { datos.filas.splice(i, 1); dibujarFilas(); marcarCambio(); },
        }, "×")))));
      actualizarPie();
    };

    guardar.addEventListener("click", async () => {
      guardar.disabled = true;
      try {
        await guardarArchivo(ruta, escribirCsv(datos), "text/csv; charset=utf-8");
        sinGuardar = false;
        for (const c of cuerpo.querySelectorAll(".cambiado")) c.classList.remove("cambiado");
        mensaje.replaceChildren(caja("exito", "Guardado."));
        if (alGuardar) await alGuardar(mensaje);
      } catch (e) {
        guardar.disabled = false;
        mensaje.replaceChildren(caja("aviso", `No pude guardar: ${e.message}`));
      }
    });

    dibujarFilas();
    contenedor.replaceChildren(
      desdeArchivo ? caja("info", "Cargado desde tu archivo. Revísalo y guarda para aplicarlo.") : "",
      el("div", { class: "tabla-envoltura editor-envoltura" }, el("table", { class: "editor" },
        el("thead", {}, el("tr", {}, el("th", { class: "num" }, "#"),
          datos.columnas.map((c) => el("th", {}, c)), el("th", {}))),
        cuerpo)),
      pie,
      el("div", { class: "acciones" },
        guardar,
        el("button", { class: "descarga", type: "button", onclick: () => {
          datos.filas.push(datos.columnas.map(() => ""));
          dibujarFilas();
          marcarCambio();
          cuerpo.lastElementChild?.querySelector(".celda")?.focus();
        } }, "+ Agregar fila"),
        el("button", { class: "descarga", type: "button",
          onclick: () => bajarComo(nombre(ruta), escribirCsv(datos)) }, "Descargar CSV"),
        botonSubir("Reemplazar con un CSV…", ".csv,text/csv", (texto) => {
          if (!descartarCambios()) return;
          montar(leerCsv(texto), true);
          sinGuardar = true;
        })),
      mensaje);
  }

  (async () => {
    if (!existe(ruta)) {
      contenedor.replaceChildren(
        caja("aviso", `Archivo no encontrado: ${nombre(ruta)}`),
        el("div", { class: "acciones" }, botonSubir(`Subir ${nombre(ruta)}`, ".csv,text/csv", (texto) => {
          montar(leerCsv(texto), true);
          sinGuardar = true;
        })));
      return;
    }
    montar(leerCsv(await leerTexto(ruta)), false);
  })().catch((e) => contenedor.replaceChildren(caja("aviso", `No pude leer ${nombre(ruta)}: ${e.message}`)));
  return contenedor;
}

/** Una tabla de solo lectura, para los CSV que escriben los scripts. */
function tablaCsv(ruta) {
  const contenedor = el("div", {}, el("p", { class: "cargando" }, "Cargando…"));
  leerTexto(ruta).then((texto) => {
    const { columnas, filas } = leerCsv(texto);
    contenedor.replaceChildren(
      el("p", { class: "nota-pie" }, `${filas.length} filas · ${columnas.length} columnas`),
      el("div", { class: "tabla-envoltura editor-envoltura" }, el("table", {},
        el("thead", {}, el("tr", {}, columnas.map((c) => el("th", {}, c)))),
        el("tbody", {}, filas.map((f) => el("tr", {}, f.map((v) => el("td", {},
          el("div", { class: "celda-lectura" }, v)))))))),
      el("div", { class: "acciones" },
        el("a", { class: "descarga", href: `${urlArchivo(ruta)}?descargar` }, "Descargar CSV")));
  }).catch((e) => contenedor.replaceChildren(caja("aviso", `No pude leer ${nombre(ruta)}: ${e.message}`)));
  return contenedor;
}

// ---------------------------------------------------------------- entregas

// Las entregas de U-Cursos vienen en un .zip general con un .zip por grupo
// adentro. Se abren acá, en el navegador, con las mismas reglas que
// extraer_entregas() de Streamlit: mismos nombres, mismos omitidos.
let jszip = null;
function cargarJsZip() {
  jszip ??= new Promise((ok, mal) => {
    const s = el("script", { src: "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js" });
    s.onload = () => ok(window.JSZip);
    s.onerror = () => { jszip = null; mal(new Error("no pude cargar el lector de .zip")); };
    document.head.append(s);
  });
  return jszip;
}

const esBasuraMac = (m) => m.split("/").includes("__MACOSX") || nombre(m).startsWith("._");
const miembroValido = (m) => !(m.includes("..") || m.startsWith("/") || m.startsWith("\\"));
const sinExtension = (m) => m.replace(/\.[^./]*$/, "");
const NO_RAR = "(.rar: el navegador no los abre; descomprímelo en tu equipo y sube los .html)";

async function extraerZip(zip, lote, prefijo = "", profundidad = 0) {
  if (profundidad > 3) return;
  const JSZip = await cargarJsZip();
  const nombres = Object.keys(zip.files).filter((m) => !esBasuraMac(m));
  const con = (ext) => nombres.filter((m) => m.toLowerCase().endsWith(ext));
  const [htmls, rmds, zips, rars] = [con(".html"), con(".rmd"), con(".zip"), con(".rar")];
  const reconocidos = new Set([...htmls, ...rmds, ...zips, ...rars]);
  const multiple = htmls.length > 1;

  for (const m of htmls) {
    if (!miembroValido(m)) { lote.omitidos.push(m); continue; }
    // Un solo HTML en el zip de un grupo: toma el nombre del zip (Grupo1.zip -> Grupo1.html).
    const destino = prefijo && !multiple ? `${prefijo}.html` : prefijo ? `${prefijo}__${nombre(m)}` : nombre(m);
    lote.archivos.push([destino, await zip.file(m).async("uint8array")]);
  }
  // El .Rmd acompaña a su HTML con el mismo nombre; con varios HTML no hay cómo aparearlos.
  if (rmds.length && prefijo && !multiple && miembroValido(rmds[0])) {
    lote.archivos.push([`${prefijo}.Rmd`, await zip.file(rmds[0]).async("uint8array")]);
  }
  for (const m of rars) lote.omitidos.push(`${m} ${NO_RAR}`);
  for (const m of zips) {
    if (!miembroValido(m)) { lote.omitidos.push(m); continue; }
    const anidado = sinExtension(m).replaceAll("/", "_");
    try {
      const interior = await JSZip.loadAsync(await zip.file(m).async("uint8array"));
      await extraerZip(interior, lote, prefijo ? `${prefijo}__${anidado}` : anidado, profundidad + 1);
    } catch {
      lote.omitidos.push(m);
    }
  }
  for (const m of nombres) {
    if (reconocidos.has(m) || m.endsWith("/") || !nombre(m)) continue;
    lote.omitidos.push(`${prefijo ? `${prefijo}/` : ""}${m} (formato no soportado — no es .html, .Rmd, .zip ni .rar)`);
  }
}

// El Worker acepta letras, números, espacios y . _ - ( ). Lo demás se cambia
// por "_" para que un nombre raro de U-Cursos no haga fallar la subida.
function nombreSeguro(n) {
  const ext = /\.rmd$/i.test(n) ? ".Rmd" : ".html";
  const base = sinExtension(n).replace(/[^\p{L}\p{N} ._\-()]/gu, "_").replace(/\.{2,}/g, "_");
  return base + ext;
}

async function procesarEntregas(tarea, ficheros, destino) {
  const lote = { archivos: [], omitidos: [] };
  destino.replaceChildren(caja("info", "Abriendo los archivos…"));
  for (const f of ficheros) {
    if (esBasuraMac(f.name)) continue;
    const n = f.name.toLowerCase();
    if (n.endsWith(".html")) lote.archivos.push([f.name, new Uint8Array(await f.arrayBuffer())]);
    else if (n.endsWith(".zip")) {
      try {
        const JSZip = await cargarJsZip();
        await extraerZip(await JSZip.loadAsync(await f.arrayBuffer()), lote);
      } catch (e) {
        lote.omitidos.push(`${f.name}${e.message.includes("lector") ? ` (${e.message})` : ""}`);
      }
    } else if (n.endsWith(".rar")) lote.omitidos.push(`${f.name} ${NO_RAR}`);
  }

  const agregados = [];
  const carpeta = `${RUTAS.entregas}${tarea}/`;
  for (const [i, [n, datos]] of lote.archivos.entries()) {
    const seguro = nombreSeguro(n);
    destino.replaceChildren(caja("info", `Subiendo ${i + 1} de ${lote.archivos.length}: ${seguro}`));
    if (existe(carpeta + seguro) || agregados.includes(seguro)) { lote.omitidos.push(seguro); continue; }
    try {
      await api(urlArchivo(carpeta + seguro), {
        method: "PUT", body: datos,
        // Una entrega ya subida no se reemplaza (el sitio responde 409).
        headers: { "content-type": seguro.endsWith(".html") ? "text/html" : "text/plain" },
      });
      agregados.push(seguro);
    } catch {
      lote.omitidos.push(seguro);
    }
  }
  archivos = await api(`/api/archivos/${encodeURIComponent(semestre)}`);

  const partes = [];
  if (agregados.length) partes.push(caja("exito", `${agregados.length} HTML(s) agregados a entregas/${tarea}/.`));
  if (lote.omitidos.length) {
    partes.push(caja("aviso", `${lote.omitidos.length} archivo(s) omitidos (ya existían o tenían una ruta `
      + `inválida dentro del zip): ${lote.omitidos.slice(0, 10).join(", ")}`));
  }
  if (!partes.length) partes.push(caja("info", "No se encontraron archivos .html para procesar."));
  destino.replaceChildren(...partes);
}

function vistaEntregas() {
  const porDefecto = valor("TAREA_DEFAULT");
  const conocidas = tareasConocidas(archivos);
  if (!conocidas.includes(porDefecto)) conocidas.push(porDefecto);
  const tarea = el("input", { type: "text", list: "tareas-conocidas", value: porDefecto, size: 6,
    pattern: "T\\d{1,2}" });
  const ficheros = el("input", { type: "file", multiple: true, accept: ".zip,.rar,.html" });
  const resultado = el("div");
  const listado = el("div");
  const boton = el("button", { class: "primario", type: "button" }, "Procesar entregas");

  const dibujarListado = () => {
    const t = tarea.value.trim();
    const htmls = archivos.filter((a) => a.ruta.startsWith(`${RUTAS.entregas}${t}/`) && a.ruta.endsWith(".html"));
    listado.replaceChildren(
      el("p", { class: "nota-pie" }, `${htmls.length} HTML(s) actualmente en entregas/${t}/.`),
      htmls.length ? el("div", { class: "tabla-envoltura editor-envoltura" }, el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "Archivo"))),
        el("tbody", {}, htmls.map((a) => el("tr", {}, el("td", {}, nombre(a.ruta))))))) : "");
  };
  tarea.addEventListener("input", dibujarListado);

  boton.addEventListener("click", async () => {
    const t = tarea.value.trim();
    if (!/^T\d{1,2}$/.test(t)) {
      resultado.replaceChildren(caja("aviso", "La tarea se escribe como T1, T2…"));
      return;
    }
    if (!ficheros.files.length) {
      resultado.replaceChildren(caja("aviso", "Elige primero los archivos."));
      return;
    }
    boton.disabled = true;
    try {
      await procesarEntregas(t, [...ficheros.files], resultado);
      ficheros.value = "";
      dibujarListado();
    } catch (e) {
      resultado.replaceChildren(caja("aviso", `No pude procesar las entregas: ${e.message}`));
    } finally {
      boton.disabled = false;
    }
  });

  dibujarListado();
  return [
    el("p", {}, "Sube las entregas de U-Cursos: un .zip con los HTML de cada grupo (puede traer un .zip "
      + "anidado por grupo, se abre automáticamente), o archivos .html sueltos."),
    el("datalist", { id: "tareas-conocidas" }, conocidas.map((t) => el("option", { value: t }))),
    el("div", { class: "fila-campos" },
      el("label", { class: "campo" }, "Tarea", tarea),
      el("label", { class: "campo" }, "Entregas (.zip, .rar o .html)", ficheros),
      boton),
    el("p", { class: "nota-pie" }, "Se guardan en entregas/<tarea>/ y no se mezclan con otras tareas. "
      + "Una entrega que ya estaba no se reemplaza."),
    resultado,
    listado,
  ];
}

// ---------------------------------------------------------------- feedback y prompts

function vistaFeedback() {
  const csvs = archivos.map((a) => a.ruta)
    .filter((r) => r.startsWith(RUTAS.salidas) && /^feedback_[^/]+\.csv$/.test(r.slice(RUTAS.salidas.length)))
    .sort();
  if (!csvs.length) {
    return [el("p", {}, "CSV de estado del pipeline de tareas. Solo lectura — es generado por los scripts."),
      caja("info", "No hay archivos de feedback todavía. Se crean al ejecutar el Paso 1 en Tareas.")];
  }
  const destino = el("div");
  const sel = el("select", {}, csvs.map((r) => el("option", { value: r }, nombre(r))));
  sel.addEventListener("change", () => destino.replaceChildren(tablaCsv(sel.value)));
  destino.replaceChildren(tablaCsv(csvs[0]));
  return [
    el("p", {}, "CSV de estado del pipeline de tareas. Solo lectura — es generado por los scripts."),
    el("label", { class: "campo" }, "Selecciona tarea", sel),
    destino,
  ];
}

function editorPrompt(ruta) {
  const contenedor = el("div", {}, el("p", { class: "cargando" }, "Cargando…"));
  leerTexto(ruta).then((texto) => {
    const area = el("textarea", { class: "prompt", spellcheck: "false" });
    area.value = texto;
    const mensaje = el("div");
    const guardar = el("button", { class: "primario", type: "button", disabled: true }, `Guardar ${nombre(ruta)}`);
    area.addEventListener("input", () => {
      sinGuardar = area.value !== texto;
      guardar.disabled = !sinGuardar;
      mensaje.replaceChildren();
    });
    guardar.addEventListener("click", async () => {
      guardar.disabled = true;
      try {
        await guardarArchivo(ruta, area.value, "text/markdown; charset=utf-8");
        texto = area.value;
        sinGuardar = false;
        mensaje.replaceChildren(caja("exito", `Guardado ${nombre(ruta)}`));
      } catch (e) {
        guardar.disabled = false;
        mensaje.replaceChildren(caja("aviso", `No pude guardar: ${e.message}`));
      }
    });
    contenedor.replaceChildren(area, el("div", { class: "acciones" }, guardar), mensaje);
  }).catch((e) => contenedor.replaceChildren(caja("aviso", `No pude leer ${nombre(ruta)}: ${e.message}`)));
  return contenedor;
}

// ---------------------------------------------------------------- contexto del curso

const CARPETA_CONTEXTO = "tareas/data/clases/";
const EXT_CONTEXTO = /\.(html|md|txt|R|r|py)$/;

/**
 * El material del curso que el modelo recibe como contexto al generar las
 * preguntas de tareas: clases renderizadas, apuntes, código. Sirve para
 * cualquier curso, no solo uno con R.
 */
function vistaContexto() {
  const lista = archivos.filter((a) => a.ruta.startsWith(CARPETA_CONTEXTO) && EXT_CONTEXTO.test(a.ruta))
    .sort((a, b) => a.ruta.localeCompare(b.ruta));
  const mensaje = el("div");
  const ficheros = el("input", { type: "file", multiple: true, accept: ".html,.md,.txt,.R,.py" });
  const subir = el("button", { class: "primario", type: "button" }, "Subir");

  subir.addEventListener("click", async () => {
    const elegidos = [...ficheros.files];
    if (!elegidos.length) { mensaje.replaceChildren(caja("aviso", "Elige primero los archivos.")); return; }
    const malos = elegidos.filter((f) => !EXT_CONTEXTO.test(f.name));
    if (malos.length) {
      mensaje.replaceChildren(caja("aviso", `Formato no admitido: ${malos.map((f) => f.name).join(", ")}. `
        + "Se aceptan .html, .md, .txt, .R y .py."));
      return;
    }
    const reemplazos = elegidos.filter((f) => existe(CARPETA_CONTEXTO + nombreContexto(f.name)));
    if (reemplazos.length && !confirm(`Ya existen y se van a reemplazar: ${reemplazos.map((f) => f.name).join(", ")}.`
      + "\nLa versión anterior queda en el historial. ¿Seguir?")) return;
    subir.disabled = true;
    const listos = [];
    try {
      for (const f of elegidos) {
        mensaje.replaceChildren(caja("info", `Subiendo ${f.name}…`));
        await guardarArchivo(CARPETA_CONTEXTO + nombreContexto(f.name), await f.arrayBuffer(),
          f.type || "application/octet-stream");
        listos.push(f.name);
      }
      dibujar();
    } catch (e) {
      mensaje.replaceChildren(caja("aviso", `Subí ${listos.length}; falló ${elegidos[listos.length]?.name}: ${e.message}`));
    } finally {
      subir.disabled = false;
    }
  });

  const borrar = async (ruta) => {
    if (!confirm(`¿Borrar ${nombre(ruta)} del contexto? Queda una copia en el historial.`)) return;
    try {
      await api(urlArchivo(ruta), { method: "DELETE" });
      archivos = await api(`/api/archivos/${encodeURIComponent(semestre)}`);
      dibujar();
    } catch (e) {
      mensaje.replaceChildren(caja("aviso", `No pude borrarlo: ${e.message}`));
    }
  };

  return [
    el("p", {}, "Material del curso que la IA recibe como contexto al generar las preguntas de tareas: clases "
      + "renderizadas (.html), apuntes (.md, .txt) o código (.R, .py). De una clase de RMarkdown se toma el código "
      + "R; de lo demás, el texto. Así las preguntas se ajustan a los métodos y el estilo del curso."),
    lista.length ? null : caja("aviso", "Este semestre no tiene contexto: las preguntas de tareas se generan sin "
      + "ver el material del curso."),
    el("div", { class: "fila-campos" }, el("label", { class: "campo" }, "Archivos", ficheros), subir),
    el("p", { class: "nota-pie" }, "Para actualizar una clase, súbela de nuevo con el mismo nombre. Cada archivo "
      + "aporta como máximo 40 mil caracteres."),
    mensaje,
    lista.length ? el("div", { class: "tabla-envoltura" }, el("table", {},
      el("thead", {}, el("tr", {}, ["Archivo", "Tamaño", "Subido", ""].map((c) => el("th", {}, c)))),
      el("tbody", {}, lista.map((a) => el("tr", {},
        el("td", {}, nombre(a.ruta)),
        el("td", {}, tamano(a.bytes)),
        el("td", {}, a.subido ? new Date(a.subido).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" }) : ""),
        el("td", {}, el("button", { class: "enlace", type: "button", onclick: () => borrar(a.ruta) }, "Borrar"))))))) : null,
  ];
}

// El Worker acepta casi cualquier nombre, pero sin \ : * ? " < > | ni "..".
function nombreContexto(n) {
  return n.replace(/[\\:*?"<>|]/g, "_").replace(/\.{2,}/g, ".");
}

// ---------------------------------------------------------------- historial

const tamano = (b) => (b == null ? "—" : b < 1024 ? `${b} B`
  : b < 1048576 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1048576).toFixed(1)} MB`);

/** Quién cambió qué archivo y cuándo, con la versión que había antes para bajarla. */
function vistaHistorial() {
  const destino = el("div", {}, el("p", { class: "cargando" }, "Cargando…"));
  const filtro = el("select", {}, el("option", { value: "" }, "Todos los archivos"));
  const dibujarTabla = (ediciones) => {
    const lista = filtro.value ? ediciones.filter((e) => e.ruta === filtro.value) : ediciones;
    destino.replaceChildren(lista.length ? el("div", { class: "tabla-envoltura editor-envoltura" }, el("table", {},
      el("thead", {}, el("tr", {}, ["Cuándo", "Archivo", "Quién", "Antes", "Después", ""].map((c) => el("th", {}, c)))),
      el("tbody", {}, lista.map((e) => el("tr", {},
        el("td", {}, new Date(e.cuando).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" })),
        el("td", {}, el("code", {}, e.ruta)),
        el("td", {}, e.quien),
        el("td", {}, tamano(e.bytes_antes)),
        el("td", {}, tamano(e.bytes_despues)),
        el("td", {}, e.hay_anterior
          ? el("a", { class: "descarga", href: `/api/version/${e.id}` }, "Bajar versión anterior")
          : el("span", { class: "tenue" }, "archivo nuevo"))))))) : caja("info", "Sin ediciones registradas."));
  };
  api(`/api/historial/${encodeURIComponent(semestre)}`).then((ediciones) => {
    const rutas = [...new Set(ediciones.map((e) => e.ruta))].sort();
    filtro.append(...rutas.map((r) => el("option", { value: r }, r)));
    filtro.addEventListener("change", () => dibujarTabla(ediciones));
    dibujarTabla(ediciones);
  }).catch((e) => destino.replaceChildren(caja("aviso", `No pude leer el historial: ${e.message}`)));
  return [
    el("p", {}, "Cada vez que un trabajo o una persona cambia un archivo del semestre, la versión anterior se "
      + "guarda aparte. Si algo quedó mal, baja la versión anterior; para restaurarla, súbela desde la pestaña "
      + "correspondiente o pídeselo a quien administra el sitio."),
    el("label", { class: "campo" }, "Archivo", filtro),
    destino,
  ];
}

function vistaPrompts() {
  const partes = [el("p", {}, "Prompts y pautas de corrección del semestre activo.")];
  for (const [proyecto, carpeta] of [["Tests Semanales", "tests_semanales/prompts/"], ["Tareas", "tareas/prompts/"]]) {
    const mds = archivos.map((a) => a.ruta)
      .filter((r) => r.startsWith(carpeta) && /^[A-Za-z0-9_-]+\.md$/.test(r.slice(carpeta.length)))
      .sort();
    if (!mds.length) continue;
    const destino = el("div", {}, editorPrompt(mds[0]));
    const sel = el("select", {}, mds.map((r) => el("option", { value: r }, nombre(r))));
    let anterior = sel.value;
    sel.addEventListener("change", () => {
      if (!descartarCambios()) { sel.value = anterior; return; }
      anterior = sel.value;
      destino.replaceChildren(editorPrompt(sel.value));
    });
    partes.push(el("h4", {}, proyecto), el("label", { class: "campo" }, "Archivo de prompt", sel), destino);
  }
  if (partes.length === 1) partes.push(caja("info", "Este semestre no tiene prompts."));
  return partes;
}

// ---------------------------------------------------------------- parámetros

const valor = (k) => parametros[k]?.valor ?? DEFECTO[k];

function quienCambio(claves) {
  const ultimos = claves.map((k) => parametros[k]).filter(Boolean)
    .sort((a, b) => b.actualizado.localeCompare(a.actualizado));
  if (!ultimos.length) return el("p", { class: "guardado-por" }, "Con los valores por defecto.");
  const u = ultimos[0];
  const cuando = new Date(u.actualizado).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" });
  return el("p", { class: "guardado-por" }, `Último cambio: ${u.por}, ${cuando}.`);
}

/** Una sección con sus campos y su propio botón Guardar, como los st.form. */
function formulario(titulo, texto, campos, leer, exito) {
  const mensaje = el("div");
  const claves = Object.keys(leer());
  const pie = el("div", {}, quienCambio(claves));
  const boton = el("button", { class: "primario", type: "button" }, "Guardar");
  boton.addEventListener("click", async () => {
    const datos = leer();
    boton.disabled = true;
    try {
      await api("/api/parametros", {
        method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(datos),
      });
      parametros = Object.fromEntries((await api("/api/parametros")).map((p) => [p.clave, p]));
      mensaje.replaceChildren(caja("exito", exito));
      pie.replaceChildren(quienCambio(claves));
    } catch (e) {
      mensaje.replaceChildren(caja("aviso", `No pude guardar: ${e.message}`));
    } finally {
      boton.disabled = false;
    }
  });
  return el("fieldset", { class: "seccion" }, el("legend", {}, titulo),
    texto ? el("p", { class: "nota-pie" }, texto) : null,
    el("div", { class: "fila-campos" }, campos),
    el("div", { class: "acciones" }, boton),
    mensaje, pie);
}

function numero(atributos) {
  return el("input", { type: "number", ...atributos });
}

function vistaParametros() {
  const modelo = el("input", { type: "text", list: "modelos", value: valor("MODELO"), size: 18 });
  const temperatura = el("input", { type: "range", min: "0", max: "1", step: "0.05", value: valor("TEMPERATURA") });
  const tempTexto = el("span", {}, Number(valor("TEMPERATURA")).toFixed(2));
  temperatura.addEventListener("input", () => { tempTexto.textContent = Number(temperatura.value).toFixed(2); });
  const maxTokens = numero({ min: "500", max: "8000", step: "100", value: valor("MAX_TOKENS") });

  const notaMin = numero({ min: "1", max: "6.9", step: "0.1", value: Number(valor("NOTA_MIN")).toFixed(1) });
  const notaMax = numero({ min: "1.1", max: "10", step: "0.1", value: Number(valor("NOTA_MAX")).toFixed(1) });
  const tareaDef = el("input", { type: "text", value: valor("TAREA_DEFAULT"), size: 6, pattern: "T\\d{1,2}" });

  const grupos = el("input", { type: "checkbox", checked: valor("GRUPO_CONTROL_TRATAMIENTO") === "true" });
  const semilla = numero({ min: "0", max: "99999", step: "1", value: valor("GRUPO_SEED") });

  const entre = (input, min, max) => Math.min(max, Math.max(min, Number(input.value)));

  return [
    el("p", { class: "nota-pie" }, "Estos parámetros son globales — se comparten entre todos los semestres. "
      + "Se aplican desde el próximo trabajo."),
    el("fieldset", { class: "seccion" }, el("legend", {}, "Credenciales"),
      el("p", {}, "La clave de OpenAI y el correo con su contraseña de aplicación viven en el motor "
        + "(Secret Manager de Google Cloud). No pasan por esta página ni por el navegador."),
      el("p", { class: "nota-pie" }, "Para cambiarlas: actualiza el .env de la raíz del proyecto y corre "
        + "motor/desplegar.ps1, que las vuelve a cargar.")),
    el("datalist", { id: "modelos" }, MODELOS_CONOCIDOS.map((m) => el("option", { value: m }))),
    formulario("Modelo OpenAI", "Aplica a ambos proyectos.", [
      el("label", { class: "campo" }, "Modelo", modelo),
      el("label", { class: "campo" }, el("span", {}, "Temperatura: ", tempTexto), temperatura),
      el("label", { class: "campo" }, "Max tokens (evaluaciones individuales)", maxTokens),
    ], () => ({
      MODELO: modelo.value.trim(),
      TEMPERATURA: String(Number(temperatura.value)),
      MAX_TOKENS: String(Math.round(entre(maxTokens, 500, 8000))),
    }), "Configuración de modelo guardada en ambos proyectos."),
    formulario("Escala de notas — Tareas", "Define el rango de notas que usa GPT para corregir.", [
      el("label", { class: "campo" }, "Nota mínima", notaMin),
      el("label", { class: "campo" }, "Nota máxima", notaMax),
      el("label", { class: "campo" }, "Tarea por defecto", tareaDef),
    ], () => ({
      NOTA_MIN: entre(notaMin, 1, 6.9).toFixed(1),
      NOTA_MAX: entre(notaMax, 1.1, 10).toFixed(1),
      TAREA_DEFAULT: tareaDef.value.trim(),
    }), "Configuración de notas guardada en Tareas."),
    formulario("Grupos control/tratamiento — Tests Semanales",
      "Cuando está activo, cada alumno es asignado aleatoriamente a un grupo y recibe la pregunta "
      + "correspondiente.", [
        el("label", { class: "campo interruptor" }, grupos, "Activar grupos control/tratamiento"),
        el("label", { class: "campo", title: "Cambiar la semilla reasigna los grupos." },
          "Semilla aleatoria (GRUPO_SEED)", semilla),
      ], () => ({
        GRUPO_CONTROL_TRATAMIENTO: grupos.checked ? "true" : "false",
        GRUPO_SEED: String(Math.round(entre(semilla, 0, 99999))),
      }), "Configuración de grupos guardada en Tests Semanales."),
  ];
}

// ---------------------------------------------------------------- semestre y estado

async function cambiarSemestre(cuerpo, mensaje) {
  try {
    await api("/api/semestres", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(cuerpo),
    });
    await cargar();
  } catch (e) {
    mensaje.replaceChildren(caja("aviso", e.message));
  }
}

function cabecera() {
  const mensaje = el("div");
  const sel = el("select", {}, semestres.map((s) => el("option", { value: s.id, selected: s.id === semestre }, s.id)));
  sel.addEventListener("change", () => {
    if (!descartarCambios()) { sel.value = semestre; return; }
    cambiarSemestre({ id: sel.value, activo: true }, mensaje);
  });
  const nuevo = el("input", { type: "text", placeholder: "2027-1", size: 12 });
  const crear = el("button", { class: "primario", type: "button" }, "Crear y activar");
  crear.addEventListener("click", () => {
    const id = nuevo.value.trim();
    if (!/^[A-Za-z0-9._-]{1,32}$/.test(id) || id.startsWith("_")) {
      mensaje.replaceChildren(caja("aviso", "Usa un identificador como 2027-1: letras, números, punto o guion."));
      return;
    }
    if (!descartarCambios()) return;
    cambiarSemestre({ id, crear: true, activo: true }, mensaje);
  });
  return [
    el("div", { class: "grilla2" },
      el("div", { class: "tarjeta" }, el("h4", {}, "Semestre activo"),
        semestres.length ? el("label", { class: "campo" }, "Semestre activo", sel)
          : caja("aviso", "No hay ningún semestre creado todavía. Crea el primero al lado →"),
        el("p", { class: "nota-pie" }, "Todas las páginas trabajan sobre el semestre activo, para todos los "
          + "que usan el sitio.")),
      el("div", { class: "tarjeta" }, el("h4", {}, "Nuevo semestre"),
        el("div", { class: "fila-campos" }, el("label", { class: "campo" }, "Identificador (ej. 2026-2)", nuevo), crear),
        el("p", { class: "nota-pie" }, "Se crea desde la plantilla, con sus prompts. No copia datos de otro "
          + "semestre."))),
    mensaje,
  ];
}

function estadoDelSistema() {
  if (!semestre) return [caja("info", "Selecciona o crea un semestre para ver su estado.")];
  const htmls = archivos.filter((a) => a.ruta.startsWith(RUTAS.entregas) && a.ruta.endsWith(".html"));
  const nTareas = new Set(htmls.map((a) => a.ruta.split("/")[3])).size;
  const item = (ok, texto) => el("li", { class: ok ? null : "falta" }, el("code", {}, texto));
  return [
    el("h4", {}, "Estado del sistema"),
    el("div", { class: "grilla2" },
      el("div", {}, el("p", { class: "nota-pie" }, "Tests Semanales"), el("ul", { class: "lista-estado" },
        item(existe(RUTAS.alumnos), "alumnos.csv"), item(existe(RUTAS.preguntas), "preguntas.csv"))),
      el("div", {}, el("p", { class: "nota-pie" }, "Tareas"), el("ul", { class: "lista-estado" },
        item(existe(RUTAS.alumnosTareas), "alumnos.csv"),
        item(htmls.length > 0, `entregas/ (${htmls.length} HTMLs en ${nTareas} tarea(s))`)))),
  ];
}

// ---------------------------------------------------------------- pantalla

const SUBPESTANAS = [
  ["alumnos", "Alumnos (Tests)", () => [
    el("p", {}, "Lista de alumnos del curso: nombre, correo y grupo. Es la que usan los tests y la reportería."),
    editorCsv(RUTAS.alumnos, { alGuardar: recalcularReporteria })]],
  ["preguntas", "Preguntas", () => [
    el("p", {}, "Preguntas, pautas y fechas de entrega por semana. Columnas: Semana, Tema, Fecha de Entrega, "
      + "Control P1/P2/P3, Control Pauta P1/P2/P3, Tratamiento P1/P2/P3, Tratamiento Pauta P1/P2/P3."),
    editorCsv(RUTAS.preguntas, { alGuardar: recalcularReporteria })]],
  ["alumnos-tareas", "Alumnos (Tareas)", () => [
    el("p", {}, "Lista de alumnos del proyecto de tareas (nombre → correo)."),
    editorCsv(RUTAS.alumnosTareas)]],
  ["entregas", "Entregas (Tareas)", vistaEntregas],
  ["feedback", "Feedback Tareas", vistaFeedback],
  ["prompts", "Prompts", vistaPrompts],
  ["contexto", "Contexto del curso", vistaContexto],
  ["historial", "Historial", vistaHistorial],
];

function barra(opciones, actual, alElegir) {
  return el("div", { class: "pestanas", role: "tablist" }, opciones.map(([id, titulo]) => el("button", {
    class: "pestana", role: "tab", type: "button", "aria-selected": String(id === actual),
    onclick: () => { if (id !== actual && descartarCambios()) alElegir(id); },
  }, titulo)));
}

function dibujar() {
  history.replaceState(null, "", pestana === "datos" ? `#datos/${sub}` : "#parametros");
  const contenido = [];
  if (pestana === "datos") {
    if (!semestre) contenido.push(caja("info", "Crea o selecciona un semestre arriba para cargar sus datos."));
    else {
      const [, , vista] = SUBPESTANAS.find(([id]) => id === sub) || SUBPESTANAS[0];
      contenido.push(barra(SUBPESTANAS, sub, (id) => { sub = id; dibujar(); }), ...vista().filter(Boolean));
    }
  } else {
    contenido.push(...vistaParametros());
  }
  app.replaceChildren(
    ...cabecera(), ...estadoDelSistema(), el("hr"),
    barra([["datos", "Datos del curso"], ["parametros", "Parámetros de la revisión"]], pestana,
      (id) => { pestana = id; dibujar(); }),
    ...contenido);
}

async function cargar() {
  try {
    const [lista, params] = await Promise.all([api("/api/semestres"), api("/api/parametros")]);
    semestres = lista;
    parametros = Object.fromEntries(params.map((p) => [p.clave, p]));
    semestre = semestres.find((s) => s.activo)?.id ?? null;
    archivos = semestre ? await api(`/api/archivos/${encodeURIComponent(semestre)}`) : [];
    sinGuardar = false;
    dibujar();
  } catch (e) {
    app.replaceChildren(caja("aviso", `No pude cargar la página: ${e.message}`));
  }
}

cargar();
