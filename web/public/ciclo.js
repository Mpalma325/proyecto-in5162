// En qué va el curso: qué semana se envió, cuál falta evaluar y qué toca
// después. Lo usan Inicio y Tests Semanales.
//
// Sale de lo guardado en la nube, no del historial de trabajos: las semanas
// que se operaron desde un PC no están en el historial.
//   enviada       = filas de notas.csv (Flujo test, Item = semana) con Enviado
//   evaluada      = las mismas filas con Nota
//   respondió sin nota = con Respondio y sin Nota
//   resumen       = existe tests_semanales/data/resumen_semana_<n>.txt
// El ciclo de cada semana es enviar y evaluar; el resumen es opcional.

import { api, el, enCuanto, fechaCorta } from "./comun.js";
import { leerCsv } from "./csv.js";
import { fechaEntrega, leerSemana, RUTA as RUTA_PREGUNTAS } from "./preguntas.js";

const VACIA = { enviados: 0, primerEnvio: "", evaluadas: 0, sinNota: 0 };

/** "2026-10-09T09:00…" -> "09/10". */
export function diaMes(iso) {
  const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}` : "";
}

/**
 * Lee el estado del semestre y lo devuelve con lo que se le pregunta:
 * estadoDe(n), enviadas(), entregaDe(n), proximoPaso(), conResumen y preguntas.
 */
export async function leerCiclo(semestre) {
  const base = `/api/archivo/${encodeURIComponent(semestre)}`;
  const [notas, resumenes, preguntas] = await Promise.all([
    fetch(`${base}/notas.csv`, { cache: "no-store" }).then((r) => {
      if (r.status === 404) return ""; // semestre nuevo: todavía no se envía nada
      if (!r.ok) throw new Error(String(r.status));
      return r.text();
    }),
    api(`/api/archivos/${encodeURIComponent(semestre)}?prefijo=${
      encodeURIComponent("tests_semanales/data/resumen_semana_")}`),
    // Para las fechas de entrega; si falla, se sigue sin ellas.
    fetch(`${base}/${RUTA_PREGUNTAS}`, { cache: "no-store" }).then((r) => (r.ok ? r.text() : "")).catch(() => ""),
  ]);
  return armarCiclo(notas, resumenes.map((a) => a.ruta), preguntas);
}

/** El ciclo a partir de los textos ya leídos (separado de la red para poder probarlo). */
export function armarCiclo(notas, rutasResumen, preguntas) {
  const porSemana = new Map();
  if (notas.trim()) {
    const { columnas, filas } = leerCsv(notas);
    const [iF, iI, iE, iR, iN] = ["Flujo", "Item", "Enviado", "Respondio", "Nota"].map((c) => columnas.indexOf(c));
    for (const f of filas) {
      const n = Number(f[iI]);
      if ((f[iF] || "").trim() !== "test" || !Number.isInteger(n) || n < 1) continue;
      const s = porSemana.get(n) || { ...VACIA };
      const enviado = (f[iE] || "").trim();
      if (enviado) {
        s.enviados++;
        if (!s.primerEnvio || enviado < s.primerEnvio) s.primerEnvio = enviado;
      }
      const nota = (f[iN] || "").trim();
      if (nota) s.evaluadas++;
      else if ((f[iR] || "").trim()) s.sinNota++;
      porSemana.set(n, s);
    }
  }
  const conResumen = new Set(rutasResumen.map((r) => Number((r.match(/resumen_semana_(\d+)\.txt$/) || [])[1]))
    .filter(Boolean));
  const tablaPreguntas = preguntas.trim() ? leerCsv(preguntas) : null;

  const estadoDe = (n) => porSemana.get(n) || VACIA;
  const enviadas = () => [...porSemana].filter(([, s]) => s.enviados).map(([n]) => n).sort((a, b) => a - b);
  const entregaDe = (n) => {
    const s = tablaPreguntas ? leerSemana(tablaPreguntas, n) : null;
    const texto = (s?.fecha || "").trim();
    return { texto, fecha: fechaEntrega(texto) };
  };

  /**
   * Lo que sigue. Si hay una semana enviada sin evaluar, evaluarla cuando
   * cierre su entrega; si no, enviar la siguiente, más o menos una semana
   * después de la anterior. { paso, semana, cuando (Date o null), ya }
   */
  const proximoPaso = (ahora = new Date()) => {
    const porEvaluar = enviadas().find((n) => !estadoDe(n).evaluadas);
    if (porEvaluar) {
      const { fecha } = entregaDe(porEvaluar);
      return { paso: "evaluar", semana: porEvaluar, cuando: fecha, ya: !fecha || fecha <= ahora };
    }
    const ultima = enviadas().at(-1);
    const siguiente = (ultima || 0) + 1;
    if (tablaPreguntas && !leerSemana(tablaPreguntas, siguiente)) return { paso: null, semana: ultima };
    const envio = ultima ? new Date(estadoDe(ultima).primerEnvio) : null;
    const cuando = envio && !Number.isNaN(envio.getTime()) ? new Date(envio.getTime() + 7 * 864e5) : null;
    return { paso: "enviar", semana: siguiente, cuando, ya: !cuando || cuando <= ahora };
  };

  const sinNota = () => [...porSemana.values()].reduce((s, x) => s + x.sinNota, 0);
  return { porSemana, conResumen, preguntas: tablaPreguntas, estadoDe, enviadas, entregaDe, proximoPaso, sinNota };
}

/**
 * Las tres flechas del ciclo abierto: enviar → la entrega → evaluar, con lo
 * hecho en verde, lo que corre ahora en azul y lo que sigue en gris.
 * `enlace(texto, paso, semana)` arma el enlace a la pestaña de Tests.
 */
export function flechasCiclo(c, enlace) {
  const p = c.proximoPaso();
  if (!p?.paso) return null;
  const n = p.semana;
  const s = c.estadoDe(n);
  const entrega = c.entregaDe(n);
  const flecha = (estado, etiqueta, valor, nota) => el("div", { class: `flecha ${estado}` },
    el("div", { class: "flecha-etiqueta" }, estado === "hecha" ? `✓ ${etiqueta}` : etiqueta),
    el("div", { class: "flecha-valor" }, valor),
    nota ? el("div", { class: "flecha-nota" }, nota) : null);
  const textoEntrega = entrega.fecha ? fechaCorta(entrega.fecha) : entrega.texto || "sin fecha";
  if (p.paso === "enviar") {
    return el("div", { class: "flechas-estado" },
      flecha("actual", "Enviar", enlace(`Semana ${n}`, "enviar", n),
        p.cuando && !p.ya ? `hacia el ${fechaCorta(p.cuando)} (${enCuanto(p.cuando)})` : "lista para enviar"),
      flecha("pendiente", "Entrega", textoEntrega, !entrega.fecha ? "sin fecha en preguntas.csv"
        : entrega.fecha < new Date() ? "ya pasó: revisa la fecha" : null),
      flecha("pendiente", "Evaluar", "Después de la entrega"));
  }
  const cerro = entrega.fecha ? entrega.fecha <= new Date() : false;
  return el("div", { class: "flechas-estado" },
    flecha("hecha", "Enviada", `${s.enviados} alumnos`, s.primerEnvio ? `el ${diaMes(s.primerEnvio)}` : null),
    flecha(cerro ? "hecha" : "actual", cerro ? "La entrega cerró" : "La entrega cierra", textoEntrega,
      entrega.fecha ? enCuanto(entrega.fecha) : "sin fecha en preguntas.csv"),
    flecha(cerro || !entrega.fecha ? "actual" : "pendiente", cerro ? "Ahora toca" : "Después",
      enlace("Evaluar las respuestas", "evaluar", n), cerro ? "esperan en el buzón del curso" : "cuando cierre la entrega"));
}
