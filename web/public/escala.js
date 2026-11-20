// La escala de notas de los tests en la página: la gemela de modulos/escala.py.
//
// El logro (puntaje sobre el máximo, de 0 a 1) pasa a nota con la escala del
// semestre, que vive en escala_notas.json (la escribe solo el trabajo
// datos.escala). Sin el archivo rige 4,0–7,0 con un decimal.
//
// Las cuentas van con fracciones exactas (BigInt) y el redondeo es hacia
// arriba en el medio, como Decimal con ROUND_HALF_UP: 5,25 → 5,3. Con floats,
// 4 + 3 × 0,0833… podría quedar en 4,2499 y redondear distinto que Python.

export const ARCHIVO = "escala_notas.json";
export const LINEAL = "lineal";
export const DOS_TRAMOS = "dos_tramos";

export const POR_DEFECTO = Object.freeze({
  tipo: LINEAL, minima: 4, maxima: 7, decimales: 1, aprobacion: null, exigencia: null, puntaje_maximo_pregunta: 3,
});

// ---------------------------------------------------------------- fracciones

const abs = (a) => (a < 0n ? -a : a);
const mcd = (a, b) => { a = abs(a); b = abs(b); while (b) [a, b] = [b, a % b]; return a || 1n; };

/** Una fracción reducida {n, d} con d > 0. */
export function fr(n, d = 1n) {
  if (d === 0n) throw new Error("división por cero");
  if (d < 0n) { n = -n; d = -d; }
  const g = mcd(n, d);
  return { n: n / g, d: d / g };
}

/** Un número leído de donde venga (número, texto con coma), sin el ruido del float. */
export function fraccion(x) {
  if (x && typeof x === "object" && typeof x.n === "bigint") return x;
  if (typeof x === "bigint") return fr(x);
  // String(0.1) es "0.1", como el repr de Python: se toma el decimal que se escribió.
  const t = String(x ?? "").trim().replace(",", ".");
  const m = t.match(/^([-+]?)(\d*)(?:\.(\d*))?(?:[eE]([-+]?\d+))?$/);
  if (!t || !m || (!m[2] && !m[3])) throw new Error(`número inválido: ${JSON.stringify(x)}`);
  const decimales = m[3] || "";
  let n = BigInt((m[2] || "0") + decimales);
  let d = 10n ** BigInt(decimales.length);
  const exp = Number(m[4] || 0);
  if (exp > 0) n *= 10n ** BigInt(exp);
  if (exp < 0) d *= 10n ** BigInt(-exp);
  return fr(m[1] === "-" ? -n : n, d);
}

export const suma = (a, b) => fr(a.n * b.d + b.n * a.d, a.d * b.d);
export const resta = (a, b) => fr(a.n * b.d - b.n * a.d, a.d * b.d);
export const por = (a, b) => fr(a.n * b.n, a.d * b.d);
export const entre = (a, b) => fr(a.n * b.d, a.d * b.n);
export const comparar = (a, b) => { const x = a.n * b.d - b.n * a.d; return x < 0n ? -1 : x > 0n ? 1 : 0; };
export const igual = (a, b) => comparar(a, b) === 0;
const piso = (a) => (a.n >= 0n ? a.n / a.d : -((-a.n + a.d - 1n) / a.d));
export const aNumero = (a) => Number(a.n) / Number(a.d);

/** 4 → "4"; 4,5 → "4,5". Como _num de escala.py, para describir la escala. */
export function numCorto(x) {
  const f = fraccion(x);
  if (f.d === 1n) return String(f.n);
  return String(aNumero(f)).replace(".", ",");
}

// ---------------------------------------------------------------- la escala

const NOMBRES = Object.keys(POR_DEFECTO);

/** La escala validada, o un Error con lo que está mal (los mismos textos que escala.py). */
export function validar(e) {
  if (![LINEAL, DOS_TRAMOS].includes(e.tipo)) throw new Error(`Tipo de escala desconocido: '${e.tipo}' (lineal o dos_tramos)`);
  const min = fraccion(e.minima);
  const max = fraccion(e.maxima);
  if (!(comparar(min, fr(0n)) >= 0 && comparar(min, max) < 0 && comparar(max, fr(1000n)) <= 0)) {
    throw new Error(`La escala va de ${e.minima} a ${e.maxima}: la mínima tiene que ser menor que la máxima, entre 0 y 1000.`);
  }
  if (![0, 1, 2].includes(e.decimales)) throw new Error(`Decimales: ${e.decimales} (0, 1 o 2)`);
  const maximoPregunta = fraccion(e.puntaje_maximo_pregunta);
  if (!(comparar(maximoPregunta, fr(0n)) > 0) || comparar(maximoPregunta, fr(100n)) > 0) {
    throw new Error("El puntaje máximo por pregunta tiene que ser mayor que cero y no pasar de 100.");
  }
  if (e.tipo === DOS_TRAMOS) {
    if (e.aprobacion === null || e.aprobacion === undefined || e.exigencia === null || e.exigencia === undefined) {
      throw new Error("Una escala de dos tramos necesita la nota de aprobación y la exigencia.");
    }
    const apr = fraccion(e.aprobacion);
    if (!(comparar(min, apr) < 0 && comparar(apr, max) < 0)) {
      throw new Error(`La aprobación (${e.aprobacion}) tiene que quedar entre la mínima y la máxima.`);
    }
    const ex = fraccion(e.exigencia);
    if (!(comparar(ex, fr(0n)) > 0 && comparar(ex, fr(1n)) < 0)) {
      throw new Error(`La exigencia (${e.exigencia}) va entre 0 y 1 (0,6 es 60 %).`);
    }
  }
  return e;
}

/** La escala desde lo leído del JSON (escala.desde_dict). Las claves que falten toman el valor por defecto. */
export function desdeDict(datos) {
  if (!datos || typeof datos !== "object" || Array.isArray(datos)) throw new Error("La escala tiene que ser un objeto JSON.");
  const extra = Object.keys(datos).filter((k) => !NOMBRES.includes(k)).sort();
  if (extra.length) throw new Error(`Claves desconocidas en la escala: ${JSON.stringify(extra)}`);
  return validar({ ...POR_DEFECTO, ...datos });
}

/** El texto de escala_notas.json (null si no existe) → { escala, error }. Ilegible: la de siempre y el error. */
export function leerEscala(texto) {
  if (texto === null || texto === undefined) return { escala: POR_DEFECTO, error: "" };
  try {
    return { escala: desdeDict(JSON.parse(String(texto).replace(/^﻿/, ""))), error: "" };
  } catch (e) {
    return { escala: POR_DEFECTO, error: `${ARCHIVO} no se entiende: ${e.message}` };
  }
}

/** El logro de una lista de puntajes: suma sobre el máximo posible. */
export function logroDe(e, puntajes) {
  if (!puntajes.length) throw new Error("Sin puntajes no hay logro.");
  const maximo = fraccion(e.puntaje_maximo_pregunta);
  let total = fr(0n);
  for (const p of puntajes.map(fraccion)) {
    if (comparar(p, fr(0n)) < 0 || comparar(p, maximo) > 0) throw new Error(`Puntaje fuera de rango: ${aNumero(p)}`);
    total = suma(total, p);
  }
  return entre(total, por(maximo, fr(BigInt(puntajes.length))));
}

/** La nota sin redondear. */
export function notaExacta(e, logro) {
  const l = fraccion(logro);
  if (comparar(l, fr(0n)) < 0 || comparar(l, fr(1n)) > 0) throw new Error(`El logro va de 0 a 1: ${aNumero(l)}`);
  const min = fraccion(e.minima);
  const max = fraccion(e.maxima);
  if (e.tipo === LINEAL) return suma(min, por(l, resta(max, min)));
  const apr = fraccion(e.aprobacion);
  const ex = fraccion(e.exigencia);
  if (comparar(l, ex) < 0) return suma(min, entre(por(resta(apr, min), l), ex));
  return suma(apr, entre(por(resta(max, apr), resta(l, ex)), resta(fr(1n), ex)));
}

/** "6,5", "83", "6,50": la nota redondeada hacia arriba en el medio, con coma (escala.texto). */
export function texto(e, nota) {
  const escala = 10n ** BigInt(e.decimales);
  const entero = piso(suma(por(fraccion(nota), fr(escala)), fr(1n, 2n)));
  if (!e.decimales) return String(entero);
  const signo = entero < 0n ? "-" : "";
  const digitos = String(abs(entero)).padStart(e.decimales + 1, "0");
  return `${signo}${digitos.slice(0, -e.decimales)},${digitos.slice(-e.decimales)}`;
}

/** La nota de ese logro, ya redondeada y con coma. */
export const nota = (e, logro) => texto(e, notaExacta(e, logro));

/** La inversa: el logro de una nota, o null si queda fuera de la escala (escala.logro). */
export function logro(e, n) {
  const x = fraccion(n);
  const min = fraccion(e.minima);
  const max = fraccion(e.maxima);
  if (comparar(x, min) < 0 || comparar(x, max) > 0) return null;
  if (e.tipo === LINEAL) return entre(resta(x, min), resta(max, min));
  const apr = fraccion(e.aprobacion);
  const ex = fraccion(e.exigencia);
  if (comparar(x, apr) < 0) return entre(por(ex, resta(x, min)), resta(apr, min));
  return suma(ex, entre(por(resta(fr(1n), ex), resta(x, apr)), resta(max, apr)));
}

/** El logro como se guarda: de 0 a 1, con cuatro decimales y punto. */
export const textoLogro = (l) => aNumero(fraccion(l)).toFixed(4);

/** Una línea: "4-7/1" o "1-7/1 4 al 60 %" (escala.describir). */
export function describir(e) {
  let base = `${numCorto(e.minima)}-${numCorto(e.maxima)}/${e.decimales}`;
  if (e.tipo === DOS_TRAMOS) base += ` ${numCorto(e.aprobacion)} al ${numCorto(por(fraccion(e.exigencia), fr(100n)))} %`;
  return base;
}

/** Para una persona: «4,0 a 7,0» (lo que va en {ESCALA} del correo de la pregunta). */
export const rango = (e) => `${texto(e, e.minima)} a ${texto(e, e.maxima)}`;

/** Los límites para un ajuste a mano: de min(1, mínima) a la máxima (2.4 del diseño). */
export const limitesAjuste = (e) => [Math.min(1, aNumero(fraccion(e.minima))), aNumero(fraccion(e.maxima))];

/**
 * Qué tiene una nota escrita a mano para esta escala: "" si está bien. Va de
 * min(1, mínima) a la máxima, con a lo más `decimales` decimales.
 */
export function problemaNota(e, textoNota) {
  const t = String(textoNota ?? "").trim();
  const [desde, hasta] = limitesAjuste(e);
  const ejemplo = texto(e, fraccion(e.maxima));
  if (!t) return "Falta la nota.";
  const decimales = e.decimales ? `([.,]\\d{1,${e.decimales}})?` : "";
  if (!new RegExp(`^\\d{1,4}${decimales}$`).test(t)) {
    return e.decimales ? `La nota se escribe con hasta ${e.decimales === 1 ? "un decimal" : "dos decimales"}, como ${ejemplo}.`
      : `La nota se escribe sin decimales, como ${ejemplo}.`;
  }
  const n = Number(t.replace(",", "."));
  if (n < desde || n > hasta) return `La nota va de ${texto(e, fraccion(desde))} a ${ejemplo}.`;
  return "";
}

/**
 * El dominio del eje de notas: de min(1, mínima) a la máxima, con un margen
 * de (máxima − mínima)/6 alrededor de los datos. Con 4–7 da lo de siempre.
 */
export function dominioNotas(valores, e = POR_DEFECTO) {
  const [desde, hasta] = limitesAjuste(e);
  const margen = (aNumero(fraccion(e.maxima)) - aNumero(fraccion(e.minima))) / 6;
  const v = valores.filter((x) => Number.isFinite(x));
  if (!v.length) return [desde, hasta];
  return [Math.max(desde, Math.floor(Math.min(...v) - margen)), Math.min(hasta, Math.ceil(Math.max(...v) + margen))];
}

// ---------------------------------------------------------------- cambiar la escala
// Configuración › Semestre: «Ver qué cambia» corre datos.escala en prueba y
// «Guardar y recalcular» lo corre en real, después de una confirmación.

/** Los logros de la tabla chica del formulario, en %: cómo queda la nota en cada uno. */
export const LOGROS_DE_MUESTRA = [0, 25, 50, 60, 75, 100];

/**
 * La escala que está escrita en el formulario: { escala, error }. Los números
 * vienen como texto, con coma o punto; la exigencia, en porcentaje (60 → 0,6).
 * El puntaje máximo por pregunta no se edita: se conserva el de la escala actual.
 */
export function escalaDelFormulario(v) {
  const numero = (t, nombre) => {
    const s = String(t ?? "").trim().replace(",", ".");
    const x = Number(s);
    if (!s || !Number.isFinite(x)) throw new Error(`Falta ${nombre} o no es un número.`);
    return x;
  };
  try {
    const dos = Boolean(v.conAprobacion);
    return {
      escala: desdeDict({
        tipo: dos ? DOS_TRAMOS : LINEAL,
        minima: numero(v.minima, "la nota mínima"),
        maxima: numero(v.maxima, "la nota máxima"),
        decimales: Number(v.decimales),
        aprobacion: dos ? numero(v.aprobacion, "la nota de aprobación") : null,
        // Con cuatro decimales: 55,5 % es 0,555 y no 0,5549999…
        exigencia: dos ? Number((numero(v.exigencia, "la exigencia") / 100).toFixed(4)) : null,
        puntaje_maximo_pregunta: v.puntajeMaximo ?? POR_DEFECTO.puntaje_maximo_pregunta,
      }),
      error: "",
    };
  } catch (e) {
    return { escala: null, error: e.message };
  }
}

/** Si dos escalas son la misma, número por número (4 y 4.0 son lo mismo). */
export function mismaEscala(a, b) {
  if (!a || !b) return false;
  return NOMBRES.every((k) => {
    const [x, y] = [a[k] ?? null, b[k] ?? null];
    if (x === null || y === null || k === "tipo") return x === y;
    return igual(fraccion(x), fraccion(y));
  });
}

/** Lo que dejó la simulación en su línea "@@escala {…}" (modulos/datos/escala_trabajo.py), o null. */
export function resumenSimulacion(salida) {
  const lineas = String(salida || "").split("\n").filter((l) => l.startsWith("@@escala "));
  if (!lineas.length) return null;
  try {
    return JSON.parse(lineas[lineas.length - 1].slice("@@escala ".length));
  } catch {
    return null;
  }
}

/**
 * El texto de la confirmación de «Guardar y recalcular», a partir de la
 * simulación. Si alguna nota que cambia ya le llegó al alumno con número
 * (`comunicadas`), `pideId` dice que además hay que escribir el id del
 * semestre: así nadie reexpresa por un clic las notas de un semestre en curso.
 */
export function confirmacionEscala(r, semestre) {
  const s = (n, uno, varios) => (n === 1 ? uno : varios);
  const partes = [
    `Se guarda la escala nueva y ${r.cambian ? `cambian ${r.cambian} ${s(r.cambian, "nota", "notas")} de Tests`
      : "no cambia ninguna nota de Tests"}.`,
  ];
  if (r.fijas) partes.push(`${r.fijas} ${s(r.fijas, "queda fija", "quedan fijas")} (fuera de la escala).`);
  if (r.media_antes && r.cambian) partes.push(`La media pasa de ${r.media_antes} a ${r.media_despues}.`);
  partes.push("No se manda ningún correo.");
  const pideId = Number(r.comunicadas) > 0;
  if (pideId) {
    partes.push(`${r.comunicadas} ${s(r.comunicadas, "nota que cambia ya le llegó", "notas que cambian ya les llegaron")} `
      + `por correo al alumno, con número. Para seguir, escribe ${semestre} en el recuadro.`);
  }
  return { texto: partes.join("\n\n"), pideId };
}

/** Si lo escrito es el id del semestre, tal cual. */
export const idConfirmado = (escrito, semestre) => String(escrito ?? "").trim() === String(semestre);
