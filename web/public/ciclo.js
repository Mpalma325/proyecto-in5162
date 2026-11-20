// En qué va el curso: qué semana se envió, cuál falta evaluar y qué toca
// después. Lo usan Inicio y Tests Semanales.
//
// Sale de lo guardado en la nube, no del historial de trabajos: las semanas
// que se operaron desde un PC no están en el historial.
//   enviada       = filas de notas.csv (Flujo test, Item = semana) con Enviado
//   evaluada      = las mismas filas con Nota (el feedback salió)
//   por revisar   = con Corregido, sin Nota ni Descartada (espera al docente)
//   descartada    = con Descartada y sin Nota (cerrada, sin feedback)
//   respondió sin nota = con Respondio y nada de lo anterior: falta corregir
//   resumen       = existe tests_semanales/data/resumen_semana_<n>.txt
// El ciclo de cada semana es enviar y evaluar; el resumen es opcional.
//
// Con preguntas.csv del formato nuevo (columna Instancia) no hay semanas: cada
// instancia trae su Envio y su Cierre, y puede haber varias abiertas a la vez.
// Lo que toca sale de esas fechas; la regla de «una semana después de la
// anterior» queda solo para el formato antiguo.
//
// modoDe(n) dice si las correcciones de esa instancia esperan al docente
// (`revisar`) o salen solas (`auto`): su columna Revision y, vacía,
// configuracion.json (modoInstancia).

import { api, el, enCuanto, fechaCorta, nombrarInstancias } from "./comun.js";
import { leerConfiguracion, modoInstancia } from "./configuracion.js";
import { leerCsv } from "./csv.js";
import {
  esLegado, fechaEntrega, leerSemana, nombreDe, RUTA as RUTA_PREGUNTAS, semanasDe, textoFecha,
} from "./preguntas.js";

// `corregidas` = evaluadas + por revisar + descartadas: lo que ya no hay que corregir.
const VACIA = { enviados: 0, primerEnvio: "", evaluadas: 0, sinNota: 0, porRevisar: 0, descartadas: 0, corregidas: 0 };

/** "2026-10-09T09:00…" -> "09/10". */
export function diaMes(iso) {
  const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}` : "";
}

/**
 * Lee el estado del semestre y lo devuelve con lo que se le pregunta:
 * estadoDe(n), enviadas(), entregaDe(n), proximoPaso(), conResumen y preguntas,
 * más legado, nombre(n) («Semana 4» o «Control 2») y mencion(n) («la semana 4»
 * o «Control 2», para meterlo en una frase).
 */
export async function leerCiclo(semestre) {
  const base = `/api/archivo/${encodeURIComponent(semestre)}`;
  const [notas, resumenes, preguntas, configuracion] = await Promise.all([
    fetch(`${base}/notas.csv`, { cache: "no-store" }).then((r) => {
      if (r.status === 404) return ""; // semestre nuevo: todavía no se envía nada
      if (!r.ok) throw new Error(String(r.status));
      return r.text();
    }),
    api(`/api/archivos/${encodeURIComponent(semestre)}?prefijo=${
      encodeURIComponent("tests_semanales/data/resumen_semana_")}`),
    // Para las fechas de entrega; si falla, se sigue sin ellas.
    fetch(`${base}/${RUTA_PREGUNTAS}`, { cache: "no-store" }).then((r) => (r.ok ? r.text() : "")).catch(() => ""),
    // El modo de respaldo de las instancias sin Revision. Sin archivo, null
    // (automático); si no se pudo leer, false: el modo no se sabe.
    fetch(`${base}/configuracion.json`, { cache: "no-store" })
      .then((r) => (r.status === 404 ? null : r.ok ? r.text() : false)).catch(() => false),
  ]);
  const c = armarCiclo(notas, resumenes.map((a) => a.ruta), preguntas, configuracion);
  // Los historiales de trabajos muestran «Control 2», no el id que va en los argumentos.
  if (!c.legado) nombrarInstancias(semanasDe(c.preguntas).map((s) => [s.numero, s.nombre]));
  return c;
}

/**
 * El ciclo a partir de los textos ya leídos (separado de la red para poder
 * probarlo). `configuracion` es el texto de configuracion.json: null si no
 * existe, false si no se pudo leer.
 */
export function armarCiclo(notas, rutasResumen, preguntas, configuracion = null) {
  const porSemana = new Map();
  if (notas.trim()) {
    const { columnas, filas } = leerCsv(notas);
    const [iF, iI, iE, iR, iN, iC, iD] = ["Flujo", "Item", "Enviado", "Respondio", "Nota", "Corregido", "Descartada"]
      .map((c) => columnas.indexOf(c));
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
      // Sin las columnas (notas.csv de antes de la fase 1) no hay por revisar ni descartadas.
      const descartada = iD >= 0 && (f[iD] || "").trim();
      const corregido = iC >= 0 && (f[iC] || "").trim();
      if (nota) s.evaluadas++;
      else if (descartada) s.descartadas++;
      else if (corregido) s.porRevisar++;
      else if ((f[iR] || "").trim()) s.sinNota++;
      if (nota || descartada || corregido) s.corregidas++;
      porSemana.set(n, s);
    }
  }
  const conResumen = new Set(rutasResumen.map((r) => Number((r.match(/resumen_semana_(\d+)\.txt$/) || [])[1]))
    .filter(Boolean));
  const tablaPreguntas = preguntas.trim() ? leerCsv(preguntas) : null;
  const legado = !tablaPreguntas || esLegado(tablaPreguntas);

  const estadoDe = (n) => porSemana.get(n) || VACIA;
  const enviadas = () => [...porSemana].filter(([, s]) => s.enviados).map(([n]) => n).sort((a, b) => a - b);
  const instancia = (n) => (tablaPreguntas ? leerSemana(tablaPreguntas, n) : null);
  const entregaDe = (n) => {
    const s = instancia(n);
    if (!legado && s?.cierre) {
      const fecha = new Date(s.cierre);
      if (!Number.isNaN(fecha.getTime())) return { texto: textoFecha(s.cierre), fecha };
    }
    const texto = (s?.fecha || "").trim();
    return { texto, fecha: fechaEntrega(texto) };
  };
  const nombre = (n) => {
    if (legado) return `Semana ${n}`;
    const s = instancia(n);
    return s ? nombreDe(s) : `Instancia ${n}`;
  };
  const mencion = (n) => (legado ? `la semana ${n}` : nombre(n));

  /**
   * Lo que sigue. Si hay una semana enviada sin evaluar, evaluarla cuando
   * cierre su entrega; si no, enviar la siguiente, más o menos una semana
   * después de la anterior. { paso, semana, cuando (Date o null), ya }
   */
  const proximoPaso = (ahora = new Date()) => {
    if (!legado) return proximoInstancia(ahora);
    const porEvaluar = enviadas().find((n) => !estadoDe(n).corregidas);
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

  /**
   * Formato nuevo: primero evaluar la enviada sin notas que cierra antes; si no
   * hay, enviar la confirmada que sale antes (`cuando` = su Envio). Si solo
   * quedan borradores, el primero, con `borrador: true` (falta confirmarlo).
   */
  const fecha = (iso) => { const d = new Date(iso || ""); return Number.isNaN(d.getTime()) ? null : d; };
  const antes = (a, b) => (a ? a.getTime() : Infinity) - (b ? b.getTime() : Infinity);
  function proximoInstancia(ahora) {
    const abiertas = enviadas().filter((n) => !estadoDe(n).corregidas)
      .map((n) => ({ n, cierre: entregaDe(n).fecha })).sort((a, b) => antes(a.cierre, b.cierre) || a.n - b.n);
    if (abiertas.length) {
      const { n, cierre } = abiertas[0];
      return { paso: "evaluar", semana: n, cuando: cierre, ya: !cierre || cierre <= ahora, abiertas: abiertas.length };
    }
    const porEnviar = semanasDe(tablaPreguntas).filter((s) => !estadoDe(s.numero).enviados);
    const confirmadas = porEnviar.filter((s) => s.estado === "confirmada")
      .map((s) => ({ n: s.numero, envio: fecha(s.envio) })).sort((a, b) => antes(a.envio, b.envio) || a.n - b.n);
    if (confirmadas.length) {
      const { n, envio } = confirmadas[0];
      return { paso: "enviar", semana: n, cuando: envio, ya: !envio || envio <= ahora };
    }
    if (porEnviar.length) return { paso: "enviar", semana: porEnviar[0].numero, cuando: null, ya: false, borrador: true };
    return { paso: null, semana: enviadas().at(-1) };
  }

  const sinNota = () => [...porSemana.values()].reduce((s, x) => s + x.sinNota, 0);
  /** [[id, cuántas], …] de las instancias con correcciones esperando revisión, en orden de cierre. */
  const porRevisar = () => [...porSemana].filter(([, x]) => x.porRevisar)
    .sort(([a], [b]) => antes(entregaDe(a).fecha, entregaDe(b).fecha) || a - b)
    .map(([n, x]) => [n, x.porRevisar]);
  // El modo de cada instancia; null si no se sabe (no se pudo leer configuracion.json y la fila no dice el suyo).
  const conf = configuracion === false ? null : leerConfiguracion(configuracion);
  const modoDe = (n) => modoInstancia(legado ? "" : instancia(n)?.revision, conf ? conf.modo : null);
  return { porSemana, conResumen, preguntas: tablaPreguntas, estadoDe, enviadas, entregaDe, proximoPaso, sinNota,
    porRevisar, legado, nombre, mencion, modoDe, configuracion: conf };
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
  const nombre = c.nombre ? c.nombre(n) : `Semana ${n}`;
  if (p.paso === "enviar") {
    const notaEnvio = p.borrador ? "en borrador: falta confirmarla"
      : p.cuando && !p.ya ? `${c.legado === false ? "sale el" : "hacia el"} ${fechaCorta(p.cuando)} (${enCuanto(p.cuando)})`
        : "lista para enviar";
    return el("div", { class: "flechas-estado" },
      flecha("actual", "Enviar", enlace(nombre, "enviar", n), notaEnvio),
      flecha("pendiente", "Entrega", textoEntrega, !entrega.fecha ? "sin fecha en preguntas.csv"
        : entrega.fecha < new Date() ? "ya pasó: revisa la fecha" : null),
      flecha("pendiente", "Evaluar", "Después de la entrega"));
  }
  const cerro = entrega.fecha ? entrega.fecha <= new Date() : false;
  const enviada = flecha("hecha", "Enviada", `${s.enviados} alumnos`, s.primerEnvio ? `el ${diaMes(s.primerEnvio)}` : null);
  // Sin fecha de entrega no hay cierre que esperar: lo que toca es evaluar cuando corresponda.
  if (!entrega.fecha) {
    return el("div", { class: "flechas-estado" }, enviada,
      flecha("pendiente", "Entrega", textoEntrega, "sin fecha en preguntas.csv"),
      flecha("actual", "Ahora toca", enlace("Evaluar las respuestas", "evaluar", n), "cuando corresponda"));
  }
  return el("div", { class: "flechas-estado" }, enviada,
    flecha(cerro ? "hecha" : "actual", cerro ? "La entrega cerró" : "La entrega cierra", textoEntrega,
      enCuanto(entrega.fecha)),
    flecha(cerro ? "actual" : "pendiente", cerro ? "Ahora toca" : "Después",
      enlace("Evaluar las respuestas", "evaluar", n), cerro ? "esperan en el buzón del curso" : "cuando cierre la entrega"));
}
