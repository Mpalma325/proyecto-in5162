// Leer y escribir CSV (RFC 4180) sin librerías, respetando el formato del
// archivo original: separador, fin de línea, BOM y dónde había comillas. Así,
// abrir un CSV en la página y guardarlo sin tocar nada deja el archivo igual.

const BOM = "﻿";

/**
 * El texto de un archivo que se sube desde la página. Excel en Windows puede
 * guardar el CSV en cp1252 en vez de UTF-8; leído como UTF-8, cada tilde y
 * cada ñ quedaría como «�» y se guardaría así. El BOM de UTF-8 se descarta,
 * igual que con File.text().
 */
export function textoDeArchivo(bytes) {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return new TextDecoder("windows-1252").decode(bytes);
  }
}

/** Texto -> { columnas, filas, formato }. `filas` son listas de strings. */
export function leerCsv(texto) {
  const bom = texto.startsWith(BOM);
  if (bom) texto = texto.slice(1);
  const primera = texto.slice(0, texto.search(/\r?\n|$/));
  const sep = (primera.match(/;/g) || []).length > (primera.match(/,/g) || []).length ? ";" : ",";
  const eol = /\r\n/.test(texto.slice(0, 5000)) ? "\r\n" : "\n";
  const finalConSalto = /\r?\n$/.test(texto);

  const registros = [];
  const citados = []; // por registro: qué campos venían entre comillas
  let fila = [], cit = [], campo = "", citado = false, entreComillas = false;
  const cerrarCampo = () => { fila.push(campo); cit.push(citado); campo = ""; citado = false; };
  const cerrarFila = () => { cerrarCampo(); registros.push(fila); citados.push(cit); fila = []; cit = []; };

  for (let i = 0; i < texto.length; i++) {
    const c = texto[i];
    if (entreComillas) {
      if (c !== '"') campo += c;
      else if (texto[i + 1] === '"') { campo += '"'; i++; }
      else entreComillas = false;
    } else if (c === '"') { entreComillas = true; citado = true; }
    else if (c === sep) cerrarCampo();
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && texto[i + 1] === "\n") i++;
      cerrarFila();
    } else campo += c;
  }
  if (campo !== "" || citado || fila.length) cerrarFila();

  const [columnas = [], ...filas] = registros;
  // Filas cortas (celdas finales vacías) se completan para que la grilla sea pareja.
  for (const f of filas) while (f.length < columnas.length) f.push("");

  // pandas pone comillas solo donde hacen falta; R, en todas las columnas de
  // texto. Se recuerda por columna: con comillas si todos sus valores las traían.
  const comillasCabecera = (citados[0] || []).slice(0, columnas.length);
  const comillasColumna = columnas.map((_, j) => {
    const vals = citados.slice(1).filter((cs, k) => filas[k][j] !== "" || cs[j]);
    return vals.length > 0 && vals.every((cs) => cs[j]);
  });
  return { columnas, filas, formato: { sep, eol, bom, finalConSalto, comillasCabecera, comillasColumna } };
}

function campoCsv(v, sep, siempre) {
  const s = v == null ? "" : String(v);
  return siempre || s.includes(sep) || s.includes('"') || s.includes("\n") || s.includes("\r")
    ? `"${s.replaceAll('"', '""')}"` : s;
}

/** { columnas, filas, formato } -> texto, con el mismo formato que se leyó. */
export function escribirCsv({ columnas, filas, formato = {} }) {
  const { sep = ",", eol = "\n", bom = false, finalConSalto = true,
    comillasCabecera = [], comillasColumna = [] } = formato;
  const lineas = [
    columnas.map((v, j) => campoCsv(v, sep, comillasCabecera[j])).join(sep),
    ...filas.map((f) => f.map((v, j) => campoCsv(v, sep, comillasColumna[j] && v !== "")).join(sep)),
  ];
  return (bom ? BOM : "") + lineas.join(eol) + (finalConSalto ? eol : "");
}

/**
 * CSV para descargar y abrir en Excel: con BOM, fines de línea de Windows y
 * sin fórmulas. Una celda que empieza con = + - @ (una respuesta de alumno,
 * por ejemplo) Excel la ejecutaría al abrir el archivo; se le antepone un
 * apóstrofo. Los números se dejan tal cual.
 */
export function exportarCsv(columnas, filas) {
  const celda = (v) => {
    let t = v === null || v === undefined ? "" : typeof v === "boolean" ? (v ? "True" : "False") : String(v);
    if (/^[=+\-@\t\r]/.test(t) && Number.isNaN(Number(t))) t = `'${t}`;
    return /[",\n\r]/.test(t) ? `"${t.replaceAll('"', '""')}"` : t;
  };
  return BOM + [columnas.map(celda).join(","), ...filas.map((f) => f.map(celda).join(","))].join("\r\n");
}

/** Descarga un texto como archivo. */
export function descargar(nombre, texto, tipo = "text/csv;charset=utf-8") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([texto], { type: tipo }));
  a.download = nombre;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
