// Configuración: la misma página de Streamlit, sobre los archivos del
// semestre en R2 y los parámetros guardados en D1.
//
// Lo que se edita acá es lo mismo que se editaba en el PC: la lista de alumnos,
// las preguntas, los prompts y las entregas. El resto de los archivos solo los
// escriben los trabajos, y el Worker rechaza cualquier otra ruta.

import {
  api, barraPestanas, caja, conDetalle, el, fechaCorta, navegacion, resumenCsv, tareasConocidas, textoEdicion,
} from "./comun.js";
import {
  contarCambios, diffLineas, filasDelLog, huella, ordenarVersiones, textoUsos, usosPorHuella, versionesDe,
} from "./historial-prompts.js";
import { escribirCsv, leerCsv } from "./csv.js";
import { editorPreguntas } from "./preguntas.js";
import { PROMPTS, problemasDePrompt } from "./prompts.js";
import { leerPrecios } from "./consumo.js";
import {
  comoCelda, decidirFila, enlaceSeguro, fechaConsulta, NOMBRE_MODELO, resumenDecisiones, textoOrigen, textoPrecio,
} from "./precios.js";
import { vistaProbarCriterio } from "./probar.js";

document.getElementById("nav").replaceWith(navegacion());
const app = document.getElementById("app");

const RUTAS = {
  alumnos: "alumnos.csv",
  preguntas: "tests_semanales/data/preguntas.csv",
  entregas: "tareas/data/entregas/",
  salidas: "tareas/data/salidas/",
};

// Los valores que usa config.py cuando nadie los cambió desde la página.
const DEFECTO = {
  MODELO: "gpt-5.4-mini", TEMPERATURA: "0.2", MAX_TOKENS: "3000",
  NOTA_MIN: "4.0", NOTA_MAX: "7.0", TAREA_DEFAULT: "T1",
  GRUPO_CONTROL_TRATAMIENTO: "true", GRUPO_SEED: "19", PRECIOS_API: "{}",
};
const MODELOS_CONOCIDOS = ["gpt-5.4-mini", "gpt-5.5", "gpt-5.4", "gpt-5.4-nano", "gpt-5-mini",
  "gpt-4o-mini", "gpt-4o"];

let semestres = [];
let semestre = null; // el activo
let archivos = []; // [{ ruta, bytes, etag }] del semestre activo
let parametros = {}; // clave -> { valor, actualizado, por }
let sinGuardar = false; // hay un editor con cambios que no se guardaron

// La dirección es #datos/<pestaña>[/<semana>]. "#parametros" era la de
// Parámetros cuando estaba aparte; sigue funcionando.
const [pestanaInicial, subInicial, semanaInicial] = location.hash.slice(1).split("/");
// Tareas › Alumnos ya no existe: Tareas usa la misma lista que los tests (alumnos.csv).
const pestanaDeHash = (p, s) => (p === "parametros" ? "parametros" : s === "alumnos-tareas" ? "alumnos" : s || "alumnos");
let sub = pestanaDeHash(pestanaInicial, subInicial);
// En Preguntas: qué semana se está viendo (#datos/preguntas/10) y si se edita
// por semana o el archivo entero como tabla.
let semanaPreguntas = Number(semanaInicial) || null;
let modoPreguntas = "semana";

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
async function guardarArchivo(ruta, cuerpo, tipo, detalle) {
  const previo = archivos.find((a) => a.ruta === ruta);
  const condicion = previo ? { "if-match": previo.etag } : { "if-none-match": "*" };
  await api(urlArchivo(ruta), {
    method: "PUT", headers: { "content-type": tipo, ...condicion, ...conDetalle(detalle) }, body: cuerpo,
  });
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
  destino.replaceChildren(caja("info", "Actualizando los resultados…"));
  try {
    const { id } = await api("/api/trabajos", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ semestre, flujo: "datos.panel", argumentos: {} }),
    });
    for (let i = 0; i < 120; i++) {
      await new Promise((ok) => setTimeout(ok, 1500));
      const t = await api(`/api/trabajos/${id}`);
      if (t.estado === "terminado") {
        destino.replaceChildren(caja("exito", "Guardado. Los resultados ya muestran los cambios."));
        return;
      }
      if (t.estado === "fallido") {
        destino.replaceChildren(caja("aviso",
          "Guardado, pero no pude actualizar los resultados. Se actualizan con el próximo trabajo."));
        return;
      }
    }
    destino.replaceChildren(caja("info", "Guardado. Los resultados se siguen actualizando."));
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
    // Cómo estaba al cargarse: para anotar en el registro qué filas cambiaron.
    let base = desdeArchivo ? datos.filas.map((f) => [...f]) : [];
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
        await guardarArchivo(ruta, escribirCsv(datos), "text/csv; charset=utf-8",
          `${nombre(ruta)}: ${resumenCsv(datos.columnas, base, datos.filas)}`);
        base = datos.filas.map((f) => [...f]);
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
    // Con integrity, como los de resultados.html: si el archivo del CDN cambiara, no se ejecuta.
    const s = el("script", {
      src: "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js",
      integrity: "sha384-+mbV2IY1Zk/X1p/nWllGySJSUN8uMs+gUAN10Or95UBH0fpj6GfKgPmgC5EXieXG", crossorigin: "anonymous",
    });
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
    if (!miembroValido(m)) { lote.omitidos.push(`${m} (ruta inválida dentro del zip)`); continue; }
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
    if (!miembroValido(m)) { lote.omitidos.push(`${m} (ruta inválida dentro del zip)`); continue; }
    const anidado = sinExtension(m).replaceAll("/", "_");
    try {
      const interior = await JSZip.loadAsync(await zip.file(m).async("uint8array"));
      await extraerZip(interior, lote, prefijo ? `${prefijo}__${anidado}` : anidado, profundidad + 1);
    } catch {
      lote.omitidos.push(`${m} (no se pudo abrir el zip)`);
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
        lote.omitidos.push(`${f.name} (${e.message.includes("lector") ? e.message : "no se pudo abrir el zip"})`);
      }
    } else if (n.endsWith(".rar")) lote.omitidos.push(`${f.name} ${NO_RAR}`);
  }

  const agregados = [];
  const carpeta = `${RUTAS.entregas}${tarea}/`;
  for (const [i, [n, datos]] of lote.archivos.entries()) {
    const seguro = nombreSeguro(n);
    destino.replaceChildren(caja("info", `Subiendo ${i + 1} de ${lote.archivos.length}: ${seguro}`));
    if (existe(carpeta + seguro) || agregados.includes(seguro)) { lote.omitidos.push(`${seguro} (ya existía)`); continue; }
    try {
      await api(urlArchivo(carpeta + seguro), {
        method: "PUT", body: datos,
        // Una entrega ya subida no se reemplaza (el sitio responde 409).
        headers: { "content-type": seguro.endsWith(".html") ? "text/html" : "text/plain",
          ...conDetalle(`Subió la entrega ${seguro} de ${tarea}`) },
      });
      agregados.push(seguro);
    } catch (e) {
      lote.omitidos.push(`${seguro} (no se pudo subir: ${e.message})`);
    }
  }
  archivos = await api(`/api/archivos/${encodeURIComponent(semestre)}`);

  const partes = [];
  if (agregados.length) partes.push(caja("exito", `${agregados.length} HTML(s) agregados a entregas/${tarea}/.`));
  if (lote.omitidos.length) {
    const mas = lote.omitidos.length > 10 ? ` y ${lote.omitidos.length - 10} más` : "";
    partes.push(caja("aviso", `${lote.omitidos.length} archivo(s) omitidos: ${lote.omitidos.slice(0, 10).join(", ")}${mas}.`));
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
  const ficheros = el("input", { type: "file", multiple: true, accept: ".zip,.html" });
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
    el("p", {}, "El .zip de U-Cursos tal como viene, o los .html sueltos."),
    el("datalist", { id: "tareas-conocidas" }, conocidas.map((t) => el("option", { value: t }))),
    el("div", { class: "fila-campos" },
      el("label", { class: "campo" }, "Tarea", tarea),
      el("label", { class: "campo" }, "Entregas (.zip o .html; los .rar hay que descomprimirlos antes)", ficheros),
      boton),
    el("p", { class: "nota-pie" }, "Una entrega que ya está no se reemplaza."),
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
    return [caja("info", "Sin registros. Se crean al generar las preguntas de una tarea.")];
  }
  const destino = el("div");
  const sel = el("select", {}, csvs.map((r) => el("option", { value: r }, nombre(r))));
  sel.addEventListener("change", () => destino.replaceChildren(tablaCsv(sel.value)));
  destino.replaceChildren(tablaCsv(csvs[0]));
  return [
    el("label", { class: "campo" }, "Tarea", sel),
    destino,
  ];
}

// ---------------------------------------------------------------- versiones anteriores de un prompt

// En el diff, de un tramo largo de líneas iguales se ven solo las que rodean
// cada cambio; el resto se abre con un botón.
const CONTEXTO_DIFF = 3;
const lineasTexto = (n) => `${n} ${n === 1 ? "línea" : "líneas"}`;

/** Lo que cambia en `version` respecto de `vigente`, con + y − además del color. */
function vistaDiff(vigente, version) {
  const { bloques, aviso } = diffLineas(vigente, version);
  const { agregadas, quitadas } = contarCambios(bloques);
  if (!agregadas && !quitadas) {
    return caja("info", "Tiene el mismo texto que la vigente, salvo espacios o saltos al principio o al final.");
  }
  const linea = (tipo, texto) => el("div", { class: `linea-diff ${tipo}` },
    el("span", { class: "signo" }, tipo === "agrega" ? "+" : tipo === "quita" ? "−" : " "),
    el("span", { class: "texto-linea" }, texto));
  const iguales = (lineas, i) => {
    const antes = i === 0 ? 0 : CONTEXTO_DIFF; // al principio del texto no hace falta contexto previo
    const despues = i === bloques.length - 1 ? 0 : CONTEXTO_DIFF;
    if (lineas.length <= antes + despues + 1) return lineas.map((l) => linea("igual", l));
    const ocultas = lineas.slice(antes, lineas.length - despues);
    const abrir = el("button", { class: "enlace", type: "button" }, `Mostrar ${lineasTexto(ocultas.length)} sin cambios`);
    const hueco = el("div", { class: "linea-diff omitidas" }, abrir);
    abrir.addEventListener("click", () => {
      // Un fragmento y no replaceWith(...lista): con muchas líneas el spread revienta la pila.
      const frag = document.createDocumentFragment();
      for (const l of ocultas) frag.append(linea("igual", l));
      hueco.replaceWith(frag);
    });
    return [...lineas.slice(0, antes).map((l) => linea("igual", l)), hueco,
      ...lineas.slice(lineas.length - despues).map((l) => linea("igual", l))];
  };
  return el("div", { class: "diff" },
    el("p", { class: "leyenda-diff" },
      agregadas ? el("span", { class: "linea-diff agrega" }, `+ ${lineasTexto(agregadas)} solo en esta versión`) : null,
      quitadas ? el("span", { class: "linea-diff quita" }, `− ${lineasTexto(quitadas)} solo en la vigente`) : null),
    aviso ? caja("aviso", aviso) : null,
    el("div", { class: "lineas-diff" }, bloques.map((b, i) => (b.tipo === "igual" ? iguales(b.lineas, i)
      : b.lineas.map((l) => linea(b.tipo, l))))));
}

/**
 * Una versión guardada: plegada, su huella y dónde se usó; abierta, el texto
 * de solo lectura, el diff con la vigente, copiarla y cargarla en el editor.
 */
function filaVersion(v, { uso, conUsos, esVigente, guardado, cargar }) {
  const cuerpo = el("div", { class: "contenido" });
  const d = el("details", { class: "version-prompt" },
    el("summary", {}, el("span", { class: "huella" }, `Versión ${v.huella}`), conUsos ? ` · ${textoUsos(uso)}` : "",
      esVigente ? el("strong", { class: "marca-vigente" }, " (la vigente)") : null),
    cuerpo);
  let cargada = null;
  d.addEventListener("toggle", () => {
    if (!d.open || cargada) return;
    cuerpo.replaceChildren(el("p", { class: "cargando" }, "Cargando…"));
    cargada = leerTexto(v.ruta).then((texto) => {
      const mensaje = el("div");
      const diff = el("div");
      const verDiff = el("button", { class: "secundario", type: "button", "aria-expanded": "false" },
        "Qué cambia respecto de la vigente");
      verDiff.addEventListener("click", () => {
        const abrir = !diff.childElementCount;
        // Contra lo guardado ahora: si se guardó otra cosa desde que se abrió, cuenta esa.
        diff.replaceChildren(...(abrir ? [vistaDiff(guardado(), texto)] : []));
        verDiff.textContent = abrir ? "Ocultar los cambios" : "Qué cambia respecto de la vigente";
        verDiff.setAttribute("aria-expanded", String(abrir));
      });
      const copiar = el("button", { class: "secundario", type: "button" }, "Copiar");
      copiar.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(texto);
          mensaje.replaceChildren(caja("exito", "Copiado."));
        } catch {
          // Sin permiso para el portapapeles (o una página sin https).
          mensaje.replaceChildren(caja("aviso", "El navegador no dejó copiar. Selecciona el texto del cuadro y cópialo a mano."));
        }
      });
      const usar = el("button", { class: "secundario", type: "button" }, "Cargar en el editor");
      usar.addEventListener("click", () => { if (descartarCambios()) cargar(texto, v.huella); });
      const fecha = (t) => fechaCorta(new Date(t));
      const cuando = !uso?.primero ? "" : uso.primero === uso.ultimo ? `, el ${fecha(uso.primero)}`
        : `, del ${fecha(uso.primero)} al ${fecha(uso.ultimo)}`;
      cuerpo.replaceChildren(...[
        uso?.eventos ? el("p", { class: "nota-pie" }, `Aparece en ${uso.eventos} ${uso.eventos === 1 ? "registro" : "registros"} `
          + `del log${cuando}.`) : null,
        el("pre", { class: "texto-version", tabindex: "0", "aria-label": `Texto de la versión ${v.huella}` }, texto),
        el("div", { class: "acciones" }, esVigente ? null : verDiff, copiar, esVigente ? null : usar),
        mensaje,
        diff].filter(Boolean));
    }).catch((e) => {
      cargada = null; // al volver a abrirla se intenta de nuevo
      cuerpo.replaceChildren(caja("aviso", `No pude leer esta versión: ${e.message}`));
    });
  });
  return d;
}

/**
 * "Versiones anteriores (N)" debajo del editor: el archivo de las versiones
 * de este prompt que corrigieron de verdad. El log y los textos se leen recién
 * al abrirla. `guardado()` es el texto guardado ahora (la vigente) y
 * `cargar(texto, huella)` lo pone en el editor como cambio sin guardar.
 */
function versionesAnteriores(ruta, versiones, { guardado, cargar }) {
  const lista = el("div", { class: "lista-versiones" }, el("p", { class: "cargando" }, "Cargando…"));
  const nodo = el("details", { class: "versiones-prompt" },
    el("summary", {}, `Versiones anteriores (${versiones.length})`),
    el("div", { class: "contenido" },
      el("p", { class: "nota-pie" }, "Cada versión se guarda la primera vez que se corrige con ella, y no se puede editar. "
        + "Para volver a una, cárgala en el editor y guarda."),
      lista));
  let usos = null; // { huella: uso }, o null si el log no se pudo leer
  let leido = null;

  async function dibujar() {
    let vigente = null;
    try { vigente = await huella(guardado()); } catch { /* sin crypto.subtle: ninguna se marca */ }
    const orden = ordenarVersiones(versiones, usos || {});
    lista.replaceChildren(...[
      usos ? null : caja("aviso", "No pude leer el registro de envíos: las versiones aparecen sin las semanas en que se usaron."),
      vigente && !versiones.some((v) => v.huella === vigente) ? el("p", { class: "nota-pie" },
        "El texto guardado ahora todavía no se usó para corregir: aparece aquí la primera vez que se use.") : null,
      ...orden.map((v) => filaVersion(v, { uso: usos?.[v.huella], conUsos: Boolean(usos), esVigente: v.huella === vigente,
        guardado, cargar }))].filter(Boolean));
  }

  nodo.addEventListener("toggle", () => {
    if (!nodo.open || leido) return;
    // Sin log todavía no hubo envíos: ninguna tiene usos, pero no es un error.
    const log = existe("log_envios.csv") ? leerTexto("log_envios.csv").then(filasDelLog) : Promise.resolve([]);
    leido = log.then((filas) => { usos = usosPorHuella(ruta, filas); }, () => { usos = null; }).then(dibujar);
  });
  // Al guardar cambia cuál es la vigente.
  return { nodo, alGuardar: () => { if (leido) leido = leido.then(dibujar); } };
}

function editorPrompt(ruta) {
  const info = PROMPTS[ruta];
  const contenedor = el("div", {}, el("p", { class: "cargando" }, "Cargando…"));
  leerTexto(ruta).then((texto) => {
    const area = el("textarea", { class: "prompt", spellcheck: "false" });
    area.value = texto;
    const mensaje = el("div");
    const guardar = el("button", { class: "primario", type: "button", disabled: true }, "Guardar cambios");
    const estadoTexto = el("span", { class: "estado-guardado" }, "Sin cambios");
    area.addEventListener("input", () => {
      sinGuardar = area.value !== texto;
      guardar.disabled = !sinGuardar;
      estadoTexto.textContent = sinGuardar ? "Cambios sin guardar" : "Sin cambios";
      estadoTexto.classList.toggle("pendiente", sinGuardar);
      mensaje.replaceChildren();
    });
    guardar.addEventListener("click", async () => {
      const problemas = problemasDePrompt(info, area.value);
      if (problemas.length && !confirm(`${problemas.join("\n\n")}\n\n¿Guardar igual?`)) return;
      guardar.disabled = true;
      try {
        await guardarArchivo(ruta, area.value, "text/markdown; charset=utf-8",
          `Editó «${info?.titulo || nombre(ruta)}»`);
        texto = area.value;
        sinGuardar = false;
        estadoTexto.textContent = "Sin cambios";
        estadoTexto.classList.remove("pendiente");
        mensaje.replaceChildren(caja("exito", "Guardado. Vale desde el próximo envío o corrección."));
        historial?.alGuardar();
      } catch (e) {
        guardar.disabled = false;
        mensaje.replaceChildren(caja("aviso", `No pude guardar: ${e.message}`));
      }
    });
    // Las variables se insertan donde está el cursor.
    const insertar = (v) => {
      const [a, b] = [area.selectionStart, area.selectionEnd];
      area.setRangeText(v, a, b, "end");
      area.focus();
      area.dispatchEvent(new Event("input"));
    };
    // Las versiones que ya corrigieron, si hay alguna. Cargar una deja su texto
    // como cambio sin guardar: se guarda con el mismo botón de siempre.
    const versiones = versionesDe(ruta, archivos);
    const historial = versiones.length ? versionesAnteriores(ruta, versiones, {
      guardado: () => texto,
      cargar: (otro, h) => {
        area.value = otro;
        area.dispatchEvent(new Event("input"));
        // Puede coincidir con lo guardado si solo difiere en espacios al principio o al final (la huella los ignora).
        mensaje.replaceChildren(area.value !== texto
          ? caja("info", `Cargaste la versión ${h}. Todavía no está guardada: revísala y guarda para usarla.`)
          : caja("info", "Es el mismo texto que está guardado ahora."));
        area.scrollIntoView({ behavior: "smooth", block: "center" });
      },
    }) : null;
    // replaceChildren, a diferencia de el(), escribe "null" si recibe null: se filtran.
    contenedor.replaceChildren(...[
      info?.uso ? el("p", {}, info.uso) : null,
      info?.variables?.length ? el("div", { class: "variables" },
        el("span", { class: "tenue" }, "Variables:"),
        info.variables.map((v) => el("button", { class: "chip", type: "button", onclick: () => insertar(v) }, v))) : null,
      info?.obligatorias ? el("p", { class: "nota-pie" }, `Tiene que conservar `
        + `${info.obligatorias.map((o) => `«${o}»`).join(" y ")}: de ahí se lee la nota.`) : null,
      info?.formato ? el("p", { class: "nota-pie" }, "Una llave literal se escribe doble: {{ o }}.") : null,
      area,
      el("div", { class: "barra-guardar" }, estadoTexto, el("span", { class: "espacio" }), guardar),
      mensaje,
      historial?.nodo].filter(Boolean));
  }).catch((e) => contenedor.replaceChildren(caja("aviso", `No pude leer ${nombre(ruta)}: ${e.message}`)));
  return contenedor;
}

// ---------------------------------------------------------------- contexto del curso

const CARPETA_CONTEXTO = "tareas/data/clases/";
const EXT_CONTEXTO = /\.(html|md|txt|r|py)$/i;

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
        const rutaNueva = CARPETA_CONTEXTO + nombreContexto(f.name);
        await guardarArchivo(rutaNueva, await f.arrayBuffer(), f.type || "application/octet-stream",
          `${existe(rutaNueva) ? "Reemplazó" : "Subió"} material del curso: ${f.name}`);
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
      await api(urlArchivo(ruta), { method: "DELETE", headers: conDetalle(`Borró material del curso: ${nombre(ruta)}`) });
      archivos = await api(`/api/archivos/${encodeURIComponent(semestre)}`);
      dibujar();
    } catch (e) {
      mensaje.replaceChildren(caja("aviso", `No pude borrarlo: ${e.message}`));
    }
  };

  return [
    el("p", {}, "Material que la IA lee al generar las preguntas de tareas: .html, .md, .txt, .R o .py. Opcional."),
    el("div", { class: "fila-campos" }, el("label", { class: "campo" }, "Archivos", ficheros), subir),
    el("p", { class: "nota-pie" }, "Un archivo con el mismo nombre reemplaza al anterior. Se usan hasta 40 mil "
      + "caracteres por archivo."),
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
      el("thead", {}, el("tr", {}, ["Cuándo", "Qué", "Archivo", "Quién", "Antes", "Después", ""]
        .map((c) => el("th", {}, c)))),
      el("tbody", {}, lista.map((e) => el("tr", {},
        el("td", {}, new Date(e.cuando).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" })),
        el("td", {}, textoEdicion(e) || el("span", { class: "tenue" }, "—")),
        el("td", {}, el("code", {}, e.ruta)),
        el("td", {}, e.quien),
        el("td", {}, tamano(e.bytes_antes)),
        el("td", {}, tamano(e.bytes_despues)),
        el("td", {}, e.hay_anterior
          ? el("a", { class: "descarga", href: `/api/version/${e.id}` }, "Bajar versión anterior")
          : el("span", { class: "tenue" }, e.ruta.includes("/") || e.ruta.includes(".") ? "archivo nuevo" : ""))))))) : caja("info", "Sin ediciones registradas."));
  };
  api(`/api/historial/${encodeURIComponent(semestre)}`).then((ediciones) => {
    const rutas = [...new Set(ediciones.map((e) => e.ruta))].sort();
    filtro.append(...rutas.map((r) => el("option", { value: r }, r)));
    filtro.addEventListener("change", () => dibujarTabla(ediciones));
    dibujarTabla(ediciones);
  }).catch((e) => destino.replaceChildren(caja("aviso", `No pude leer el historial: ${e.message}`)));
  return [
    el("label", { class: "campo" }, "Archivo", filtro),
    destino,
  ];
}

// Qué prompt se está viendo, entre redibujos de la página.
let promptElegido = null;

function vistaPrompts() {
  const grupos = [["Tests Semanales", "tests_semanales/prompts/"], ["Tareas", "tareas/prompts/"]]
    .map(([proyecto, carpeta]) => [proyecto, archivos.map((a) => a.ruta)
      .filter((r) => r.startsWith(carpeta) && /^[A-Za-z0-9_-]+\.md$/.test(r.slice(carpeta.length))).sort()])
    .filter(([, mds]) => mds.length);
  const todas = grupos.flatMap(([, mds]) => mds);
  if (!todas.length) return [caja("info", "Este semestre no tiene prompts.")];
  // Sin elegir, el que más se revisa: cómo corrige la IA.
  if (!todas.includes(promptElegido)) {
    promptElegido = todas.find((r) => r.endsWith("/evaluar_respuesta.md")) ?? todas[0];
  }

  const destino = el("div", {}, editorPrompt(promptElegido));
  // Un solo selector, con el nombre de lo que hace cada prompt y su archivo entre paréntesis.
  const sel = el("select", { class: "selector-prompt" }, grupos.map(([proyecto, mds]) => el("optgroup", { label: proyecto },
    mds.map((r) => el("option", { value: r, selected: r === promptElegido },
      PROMPTS[r] ? `${PROMPTS[r].titulo} (${nombre(r)})` : nombre(r))))));
  sel.addEventListener("change", () => {
    if (!descartarCambios()) { sel.value = promptElegido; return; }
    promptElegido = sel.value;
    destino.replaceChildren(editorPrompt(sel.value));
  });
  return [
    el("label", { class: "campo" }, "Prompt", sel),
    destino,
  ];
}

// ---------------------------------------------------------------- parámetros

const valor = (k) => parametros[k]?.valor ?? DEFECTO[k];

function quienCambio(claves) {
  const ultimos = claves.map((k) => parametros[k]).filter(Boolean)
    .sort((a, b) => b.actualizado.localeCompare(a.actualizado));
  if (!ultimos.length) return el("p", { class: "guardado-por" }, "Valores por defecto.");
  const u = ultimos[0];
  const cuando = new Date(u.actualizado).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" });
  return el("p", { class: "guardado-por" }, `Último cambio: ${u.por}, ${cuando}`);
}

// Secciones de Parámetros con cambios sin guardar; sinGuardar es verdadero si hay alguna.
const parametrosSinGuardar = new Set();

/**
 * Una sección con sus campos y su propio botón Guardar, como los st.form.
 * Avisa en la sección misma si hay cambios sin guardar, y los suma al aviso
 * de la página para que cambiar de pestaña no los pierda en silencio.
 */
function formulario(titulo, texto, campos, leer, exito) {
  const mensaje = el("div");
  const claves = Object.keys(leer());
  const pie = el("div", {}, quienCambio(claves));
  const boton = el("button", { class: "primario", type: "button", disabled: true }, "Guardar");
  const estado = el("span", { class: "estado-guardado" }, "Sin cambios");
  let guardado = JSON.stringify(leer());
  const revisar = () => {
    const hay = JSON.stringify(leer()) !== guardado;
    if (hay) parametrosSinGuardar.add(titulo); else parametrosSinGuardar.delete(titulo);
    sinGuardar = parametrosSinGuardar.size > 0;
    // Con un campo inválido, Guardar sigue activo: al pulsarlo dice qué corregir.
    const invalido = [...seccion.querySelectorAll("input")].some((i) => !i.checkValidity());
    estado.textContent = invalido ? "Hay un valor fuera de rango" : hay ? "Cambios sin guardar" : "Sin cambios";
    estado.classList.toggle("pendiente", hay || invalido);
    boton.disabled = !hay && !invalido;
  };
  boton.addEventListener("click", async () => {
    // Un valor fuera de rango se dice junto al campo, en vez de guardarse ajustado en silencio.
    const malo = [...seccion.querySelectorAll("input")].find((i) => !i.checkValidity());
    if (malo) { malo.reportValidity(); return; }
    const datos = leer();
    boton.disabled = true;
    try {
      await api("/api/parametros", {
        method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(datos),
      });
      parametros = Object.fromEntries((await api("/api/parametros")).map((p) => [p.clave, p]));
      guardado = JSON.stringify(datos);
      mensaje.replaceChildren(caja("exito", exito));
      pie.replaceChildren(quienCambio(claves));
    } catch (e) {
      mensaje.replaceChildren(caja("aviso", `No pude guardar: ${e.message}`));
    } finally {
      revisar();
    }
  });
  const seccion = el("fieldset", { class: "seccion" }, el("legend", {}, titulo),
    texto ? el("p", { class: "nota-pie" }, texto) : null,
    el("div", { class: "fila-campos" }, campos),
    el("div", { class: "acciones" }, boton, estado),
    mensaje, pie);
  seccion.addEventListener("input", revisar);
  seccion.addEventListener("change", revisar);
  return seccion;
}

/** Un campo con su explicación debajo, a la vista (en celular no hay "pasar el mouse"). */
function campoExplicado(etiqueta, control, explicacion) {
  return el("label", { class: "campo campo-explicado" }, etiqueta, control,
    el("span", { class: "explicacion" }, explicacion));
}

function numero(atributos) {
  return el("input", { type: "number", ...atributos });
}

/**
 * Los precios de la API por modelo, para mostrar cuánto cuesta cada trabajo.
 * Una fila por modelo conocido, más las que se agreguen; las vacías no se guardan. Devuelve [tabla, leer].
 */
function camposPrecios() {
  const actuales = leerPrecios(valor("PRECIOS_API"));
  const modelos = [...new Set([valor("MODELO"), ...Object.keys(actuales), ...MODELOS_CONOCIDOS])];
  const nuevaFila = (m) => {
    // step "any": hay precios de cuatro decimales (0.0375) y con step 0.001 el navegador no deja guardarlos.
    // La caché es opcional: vacía, se cobra como entrada.
    const [entrada, salida, cache] = [0, 1, 2].map((i) => actuales[m]?.[i] ?? "").map((x) => el("input", {
      type: "number", min: "0", step: "any", value: x === "" ? "" : String(x), "aria-label": m }));
    // Una fila a medias no se guarda: se avisa en vez de descartarla callada.
    const revisarFila = () => {
      const medias = (entrada.value === "") !== (salida.value === "")
        || (cache.value !== "" && (entrada.value === "" || salida.value === ""));
      for (const x of [entrada, salida]) {
        x.setCustomValidity(medias && x.value === "" ? `Completa Entrada y Salida de ${m}, o deja la fila vacía.` : "");
      }
    };
    for (const x of [entrada, salida, cache]) x.addEventListener("input", revisarFila);
    // Debajo de la fila, lo que sugiere «Traer precios». Oculta hasta entonces.
    const nota = el("td", { colspan: "4" });
    const filaNota = el("tr", { class: "nota-precio", hidden: true }, nota);
    return { m, entrada, salida, cache, nota, filaNota };
  };
  const filas = modelos.map(nuevaFila);
  const enTabla = (f) => [el("tr", {}, el("td", {}, el("code", {}, f.m)), el("td", {}, f.entrada),
    el("td", {}, f.salida), el("td", {}, f.cache)), f.filaNota];
  const cuerpo = el("tbody", {}, filas.map(enTabla));
  const tabla = el("div", { class: "tabla-envoltura precios" }, el("table", {},
    el("thead", {}, el("tr", {}, ["Modelo", "Entrada", "Salida", "En caché"].map((c) => el("th", {}, c)))), cuerpo));
  // Sin caché se guardan dos valores, como antes; con ella, tres.
  const leer = () => ({ PRECIOS_API: JSON.stringify(Object.fromEntries(filas
    .filter((f) => f.entrada.value !== "" && f.salida.value !== "")
    .map((f) => [f.m, [f.entrada.value, f.salida.value, ...(f.cache.value !== "" ? [f.cache.value] : [])].map(Number)]))) });
  const agregar = (m) => {
    const f = nuevaFila(m);
    filas.push(f);
    cuerpo.append(...enTabla(f));
    return f;
  };
  return [el("div", { class: "campos-precios" }, botonTraerPrecios(filas), tabla, agregarModelo(filas, agregar)), leer];
}

/**
 * Una fila para un modelo que no está en la tabla (al cambiar de proveedor, o
 * uno que Inicio dice que falta). Vacía no se guarda, como las demás.
 */
function agregarModelo(filas, agregar) {
  const nombre = el("input", { type: "text", list: "modelos", size: 22, "aria-label": "Modelo para agregar",
    placeholder: "otro modelo" });
  const boton = el("button", { class: "secundario", type: "button" }, "Agregar fila");
  const mensaje = el("span", { class: "nota-pie" });
  const sumar = () => {
    const m = nombre.value.trim();
    if (!NOMBRE_MODELO.test(m)) {
      mensaje.textContent = "Ese nombre no sirve: de 2 a 60 letras, números, punto, guion, dos puntos o barra.";
      nombre.focus();
      return;
    }
    mensaje.textContent = "";
    nombre.value = "";
    (filas.find((f) => f.m === m) || agregar(m)).entrada.focus();
  };
  boton.addEventListener("click", sumar);
  nombre.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); sumar(); } });
  return el("div", { class: "acciones" }, nombre, boton, mensaje);
}

/** Escribe en una celda como si lo hubiera tecleado: así el formulario ve el cambio. */
function escribir(input, texto) {
  input.value = texto;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

/**
 * «Traer precios»: pide al sitio los de cada modelo de la tabla y llena solo
 * las celdas vacías (public/precios.js decide fila por fila). No guarda nada.
 */
function botonTraerPrecios(filas) {
  const boton = el("button", { class: "secundario", type: "button" }, "Traer precios");
  const mensaje = el("div");
  boton.addEventListener("click", async () => {
    boton.disabled = true;
    boton.textContent = "Buscando…";
    // Lo de una consulta anterior se borra: si esta falla, no queda a la vista como si fuera nuevo.
    for (const f of filas) f.filaNota.hidden = true;
    mensaje.replaceChildren();
    try {
      const r = await api(`/api/precios-sugeridos?modelos=${encodeURIComponent(filas.map((f) => f.m).join(","))}`);
      // Lo guardado se lee ahora: después de un Guardar la vista no se rearma.
      const guardados = leerPrecios(valor("PRECIOS_API"));
      const decisiones = filas.map((f) => mostrarSugerencia(f, guardados[f.m], r.modelos?.[f.m] ?? null,
        r.dudas?.[f.m] ?? null));
      mensaje.replaceChildren(el("div", { class: "info" }, origenDeLosPrecios(r), " ", resumenDecisiones(decisiones)),
        ...(r.avisos || []).map((a) => caja("aviso", a)));
    } catch (e) {
      mensaje.replaceChildren(caja("aviso", `No pude traer los precios: ${e.message} La tabla quedó como estaba.`));
    } finally {
      boton.disabled = false;
      boton.textContent = "Traer precios";
      // Al deshabilitarlo el foco se fue al body: vuelve para quien usa el teclado.
      boton.focus();
    }
  });
  return el("div", {}, el("div", { class: "acciones" }, boton,
    el("span", { class: "nota-pie" }, "Los busca en listas públicas; revísalos antes de guardar.")), mensaje);
}

/** "Según genai-prices, consultado el 02-11-2026." con el enlace a cada fuente. */
function origenDeLosPrecios(r) {
  const fuentes = r.fuentes || [];
  if (!fuentes.length) return "Ninguna fuente respondió.";
  const enlaces = fuentes.map((f) => {
    const href = enlaceSeguro(f.enlace);
    return href ? el("a", { href, target: "_blank", rel: "noopener" }, f.nombre) : f.nombre;
  });
  const unidos = enlaces.flatMap((x, i) => (i === 0 ? [x] : [i === enlaces.length - 1 ? " y " : ", ", x]));
  return el("span", {}, "Según ", unidos, `, consultado el ${fechaConsulta(fuentes[0].consultado)}.`);
}

/** La sugerencia de una fila, debajo de ella. Devuelve lo que se decidió. */
function mostrarSugerencia(f, guardado, sugerido, duda) {
  const d = decidirFila({ entrada: f.entrada.value, salida: f.salida.value, cache: f.cache.value }, guardado, sugerido,
    duda);
  f.filaNota.hidden = false;
  if (d.accion === "sin-dato" || d.accion === "ambiguo") {
    f.nota.replaceChildren(d.accion === "ambiguo" ? "La fuente lo trae a varios precios (mira el aviso de arriba): queda como está."
      : "La fuente no trae este modelo: queda como está.");
    return d;
  }
  if (d.accion === "llenar") {
    if (f.entrada.value === "") escribir(f.entrada, d.entrada);
    if (f.salida.value === "") escribir(f.salida, d.salida);
    if (f.cache.value === "" && d.cache) escribir(f.cache, d.cache);
  }
  const href = enlaceSeguro(sugerido.enlace);
  const origen = href ? el("a", { href, target: "_blank", rel: "noopener" }, textoOrigen(sugerido)) : textoOrigen(sugerido);
  const usar = el("button", { class: "enlace", type: "button" }, "Usar");
  usar.addEventListener("click", () => {
    escribir(f.entrada, comoCelda(sugerido.entrada));
    escribir(f.salida, comoCelda(sugerido.salida));
    // Sin caché en la fuente, la celda se vacía (se cobra como entrada, como
    // dice elegir()): la de la tarifa anterior no corresponde a la nueva.
    if (typeof sugerido.cache === "number" && Number.isFinite(sugerido.cache)) escribir(f.cache, comoCelda(sugerido.cache));
    else if (f.cache.value !== "") escribir(f.cache, "");
    // El botón desaparece: el foco pasa a la fila en vez de caer al body.
    f.entrada.focus();
    usar.replaceWith(el("span", {}, "usado"));
  });
  const que = { llenar: "Sugerido", igual: "Coincide con", distinta: "Sugerido" }[d.accion];
  // Por el(): replaceChildren escribiría "null" y las listas como texto.
  f.nota.replaceChildren(el("span", {},
    d.accion === "igual" ? `${que} ` : `${que}: ${textoPrecio(sugerido)} · `, origen,
    d.accion === "distinta" ? [" · ", usar] : null,
    d.revisar ? el("span", { class: "revisar" }, ` ⚠ ${d.revisar}`) : null));
  return d;
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

  parametrosSinGuardar.clear();
  const [precios, leerPrecios_] = camposPrecios();
  return [
    el("p", { class: "nota-pie" }, "Valen para todos los semestres, desde el próximo trabajo."),
    el("datalist", { id: "modelos" }, MODELOS_CONOCIDOS.map((m) => el("option", { value: m }))),
    formulario("Modelo", null, [
      campoExplicado("Modelo", modelo, `Por defecto, ${DEFECTO.MODELO}.`),
      campoExplicado(el("span", {}, "Temperatura: ", tempTexto), temperatura,
        `Más baja, más pareja. Por defecto, ${DEFECTO.TEMPERATURA}.`),
      campoExplicado("Máximo de tokens por respuesta", maxTokens,
        `Súbelo si el feedback llega cortado. Por defecto, ${DEFECTO.MAX_TOKENS}.`),
    ], () => ({
      MODELO: modelo.value.trim(),
      TEMPERATURA: String(Number(temperatura.value)),
      MAX_TOKENS: String(Math.round(entre(maxTokens, 500, 8000))),
    }), "Guardado."),
    formulario("Escala de las tareas", null, [
      el("label", { class: "campo" }, "Nota mínima", notaMin),
      el("label", { class: "campo" }, "Nota máxima", notaMax),
      el("label", { class: "campo" }, "Tarea por defecto", tareaDef),
    ], () => ({
      NOTA_MIN: entre(notaMin, 1, 6.9).toFixed(1),
      NOTA_MAX: entre(notaMax, 1.1, 10).toFixed(1),
      TAREA_DEFAULT: tareaDef.value.trim(),
    }), "Guardado."),
    formulario("Grupos Control y Tratamiento", "Cada alumno recibe la versión de la pregunta de su grupo.", [
        el("label", { class: "campo interruptor" }, grupos, "Usar dos grupos (Control y Tratamiento)"),
        campoExplicado("Semilla del sorteo", semilla, "Solo afecta a quienes aún no tienen grupo."),
      ], () => ({
        GRUPO_CONTROL_TRATAMIENTO: grupos.checked ? "true" : "false",
        GRUPO_SEED: String(Math.round(entre(semilla, 0, 99999))),
      }), "Guardado."),
    formulario("Precios de la API", "US$ por millón de tokens, los de la página de precios de tu proveedor. "
      + "Sirven para mostrar cuánto costó cada trabajo; sin precio se muestran los tokens. "
      + "«En caché» es el precio de la entrada que el proveedor reutiliza (cached input); si la dejas vacía, se cobra como entrada.",
      [precios], leerPrecios_,
      "Guardado."),
    el("details", { class: "para-admin" },
      el("summary", {}, "Credenciales"),
      el("div", { class: "contenido" },
        el("p", {}, "La clave de OpenAI y el correo con su contraseña de aplicación viven en el motor "
          + "(Secret Manager de Google Cloud). No pasan por esta página ni por el navegador."),
        el("p", { class: "nota-pie" }, "Para cambiarlas: actualiza el .env de la raíz del proyecto y corre "
          + "motor/desplegar.ps1, que las vuelve a cargar."))),
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

/** Ir a una pestaña, sin perder en silencio lo que no se guardó. */
function irA(id) {
  if (id === sub || !descartarCambios()) return;
  sub = id;
  dibujar();
}

// Cambiar solo el # (un marcador, la barra de direcciones) también cambia de
// pestaña. Si se queda donde estaba por cambios sin guardar, el # vuelve.
addEventListener("hashchange", () => {
  const [p, s, sem] = location.hash.slice(1).split("/");
  const id = pestanaDeHash(p, s);
  const semana = id === "preguntas" && Number(sem) ? Number(sem) : semanaPreguntas;
  if (id === sub && semana === semanaPreguntas) return;
  if (!PESTANAS.some(([x]) => x === id) || !descartarCambios()) {
    history.replaceState(null, "", `#datos/${sub}`);
    return;
  }
  sub = id;
  semanaPreguntas = semana;
  dibujar();
});

/** Arriba de todo, en una línea: el semestre activo, si le falta algo, y crear otro. */
function cabecera() {
  const mensaje = el("div");
  const sel = el("select", {}, semestres.map((s) => el("option", { value: s.id, selected: s.id === semestre }, s.id)));
  sel.addEventListener("change", () => {
    if (!descartarCambios()) { sel.value = semestre; return; }
    // El semestre activo es uno para todos, también para las tareas programadas.
    if (!confirm(`Desde ahora el sitio y las tareas programadas (como las respuestas a dudas) usan ${sel.value} `
      + "para todos los docentes. ¿Activarlo?")) { sel.value = semestre; return; }
    cambiarSemestre({ id: sel.value, activo: true }, mensaje);
  });
  const nuevo = el("input", { type: "text", placeholder: "2027-1", size: 12 });
  const crear = el("button", { class: "secundario", type: "button" }, "Crear y activar");
  crear.addEventListener("click", () => {
    const id = nuevo.value.trim();
    if (!/^[A-Za-z0-9._-]{1,32}$/.test(id) || id.startsWith("_")) {
      mensaje.replaceChildren(caja("aviso", "Usa un identificador como 2027-1: letras, números, punto o guion."));
      return;
    }
    if (!descartarCambios()) return;
    if (semestre && !confirm(`Se crea ${id} desde la plantilla y queda activo para todos, en lugar de ${semestre}, `
      + "también para las tareas programadas. ¿Crear y activar?")) return;
    // Mientras copia la plantilla, el botón no se puede volver a apretar.
    crear.disabled = true;
    crear.textContent = "Creando…";
    cambiarSemestre({ id, crear: true, activo: true }, mensaje).finally(() => {
      crear.disabled = false;
      crear.textContent = "Crear y activar";
    });
  });
  const nuevoSemestre = el("details", { class: "nuevo-semestre", open: !semestres.length },
    el("summary", {}, "Nuevo semestre…"),
    el("div", { class: "contenido" },
      el("div", { class: "fila-campos" }, el("label", { class: "campo" }, "Identificador (ej. 2027-1)", nuevo), crear),
      el("p", { class: "nota-pie" }, "Se crea desde la plantilla y queda activo para todos.")));
  return [
    el("div", { class: "barra-semestre" },
      semestres.length ? el("label", { class: "campo-en-linea" }, "Semestre activo", sel)
        : caja("aviso", "Todavía no hay ningún semestre: crea el primero."),
      estadoDelSemestre(),
      nuevoSemestre),
    mensaje,
  ];
}

/** Si al semestre le falta algo para operar, dicho en una línea y con enlace a dónde se arregla. */
function estadoDelSemestre() {
  if (!semestre) return null;
  const htmls = archivos.filter((a) => a.ruta.startsWith(RUTAS.entregas) && a.ruta.endsWith(".html"));
  const nTareas = new Set(htmls.map((a) => a.ruta.split("/")[3])).size;
  const faltan = [["alumnos", "falta la lista de alumnos", existe(RUTAS.alumnos)],
    ["preguntas", "faltan las preguntas", existe(RUTAS.preguntas)]].filter(([, , ok]) => !ok);
  const enlace = (id, texto) => el("a", { class: "marca-estado falta", href: `#datos/${id}`,
    onclick: (e) => { e.preventDefault(); irA(id); } }, `⚠ ${texto}`);
  return el("div", { class: "estado-semestre" },
    faltan.length ? faltan.map(([id, texto]) => enlace(id, texto))
      : el("span", { class: "marca-estado ok" }, "✓ Alumnos y preguntas cargados"),
    el("span", { class: "marca-estado" }, htmls.length
      ? `Tareas: ${htmls.length} entrega${htmls.length === 1 ? "" : "s"} en ${nTareas} tarea${nTareas === 1 ? "" : "s"}`
      : "Tareas: sin entregas"));
}

// ---------------------------------------------------------------- preguntas

function vistaPreguntas() {
  const modos = el("div", { class: "chips modos" }, [["semana", "Por semana"], ["tabla", "Tabla completa"]]
    .map(([id, texto]) => el("button", {
      type: "button", class: "chip", "aria-pressed": String(id === modoPreguntas),
      onclick: () => { if (id !== modoPreguntas && descartarCambios()) { modoPreguntas = id; dibujar(); } },
    }, texto)));
  if (modoPreguntas === "tabla") {
    return [modos,
      editorCsv(RUTAS.preguntas, { alGuardar: recalcularReporteria })];
  }
  return [modos,
    editorPreguntas({
      semestre, semana: semanaPreguntas,
      usaGrupos: valor("GRUPO_CONTROL_TRATAMIENTO") !== "false",
      alCambiarSemana: (n) => { semanaPreguntas = n; history.replaceState(null, "", `#datos/preguntas/${n}`); },
      alCambiar: (hay) => { sinGuardar = hay; },
      // La reportería no lee preguntas.csv: no hay nada que recalcular. Sí se
      // refresca la lista de archivos, porque la tabla completa guarda con su
      // etag y sin esto chocaría con el guardado que se acaba de hacer.
      alGuardar: async () => { archivos = await api(`/api/archivos/${encodeURIComponent(semestre)}`); },
    })];
}

// ---------------------------------------------------------------- pantalla

// Las pestañas, agrupadas por para qué se usan. Los ids son los de siempre:
// van en la dirección (#datos/<id>) y otras páginas enlazan a ellos.
const SECCIONES = [
  ["Tests semanales", [
    ["alumnos", "Alumnos", () => [editorCsv(RUTAS.alumnos, { alGuardar: recalcularReporteria })]],
    ["preguntas", "Preguntas", vistaPreguntas],
  ]],
  ["Tareas", [
    ["entregas", "Entregas", vistaEntregas],
    ["feedback", "Feedback", vistaFeedback],
    ["contexto", "Contexto", vistaContexto],
  ]],
  ["La IA", [
    ["prompts", "Prompts", vistaPrompts],
    ["probar", "Probar criterio", () => vistaProbarCriterio({ semestre, archivos, alCambiar: (hay) => { sinGuardar = hay; } })],
    ["parametros", "Parámetros", vistaParametros],
  ]],
  ["Registro", [
    ["historial", "Historial", vistaHistorial],
  ]],
];
const PESTANAS = SECCIONES.flatMap(([, ps]) => ps);

function pestanasDatos() {
  return barraPestanas({
    etiqueta: "Secciones de datos", actual: sub, alElegir: irA,
    grupos: SECCIONES.map(([rotulo, ps]) => ({ rotulo, pestanas: ps.map(([id, titulo]) => ({ id, titulo })) })),
  });
}

function dibujar() {
  const actual = PESTANAS.find(([id]) => id === sub) || PESTANAS[0];
  sub = actual[0];
  const [, , vista] = actual;
  const conSemana = sub === "preguntas" && modoPreguntas === "semana" && semanaPreguntas ? `/${semanaPreguntas}` : "";
  history.replaceState(null, "", `#datos/${sub}${conSemana}`);
  // Parámetros no depende del semestre: valen para todos.
  const sinSemestre = !semestre && sub !== "parametros";
  app.replaceChildren(
    ...cabecera(),
    pestanasDatos(),
    ...(sinSemestre ? [caja("info", "Crea o elige un semestre arriba para cargar sus datos.")] : vista().filter(Boolean)));
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
