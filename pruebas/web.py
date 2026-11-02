"""
El sitio web calcula exactamente lo mismo que Streamlit.

La página no reimplementa las métricas: corre modulos/datos/agregaciones.py con
Pyodide, a través de un puente escrito en app.js. Acá se ejecuta ese mismo
puente con Python normal, sobre los semestres reales, y se compara carácter por
carácter contra lo que calcula reportes.py. No usa red ni navegador.

Los tres problemas que motivaron esto aparecieron al construir el sitio:
- JavaScript serializa 7.0 como 7, y la página mostraba "7" donde Streamlit
  muestra "7.0".
- El orden de los alumnos empatados en nota dependía del orden de las filas de
  entrada, y la base de datos las devuelve en otro orden que los CSV.
- El Worker devolvía las columnas en otro orden, y el CSV descargado salía con
  las columnas cambiadas.

También revisa que la página de datos guarde los CSV sin alterarlos, y que las
listas que se repiten entre el Worker, el motor y la página no se desalineen.
"""

import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import check, resultado, titulo

from modulos import semestre
from modulos.datos import reportes

RAIZ = Path(".")
AGREGACIONES = RAIZ / "modulos" / "datos" / "agregaciones.py"
APP_JS = RAIZ / "web" / "public" / "app.js"
WORKER = RAIZ / "web" / "src" / "index.ts"

FUNCIONES = ("resumen", "por_item", "por_grupo", "por_alumno", "distribucion_notas",
             "distribucion_originalidad", "originalidad_por_item", "originalidad_vs_nota",
             "correlacion_originalidad_nota", "sin_responder", "pendientes_de_evaluar",
             "correlaciones_por_alumno", "correlaciones_por_respuesta")


def como_javascript(filas):
    """Lo que llega a la página: JSON que pasó por JavaScript, que no distingue 7 de 7.0."""
    def js(v):
        return int(v) if isinstance(v, float) and v.is_integer() else v
    return json.dumps([{k: js(v) for k, v in f.items()} for f in filas], ensure_ascii=False)


titulo("1. agregaciones.py no depende de nada del proyecto")
arbol = ast.parse(AGREGACIONES.read_text(encoding="utf-8"))
propios = [n for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)
           and (n.level > 0 or (n.module or "").startswith("modulos"))]
check("sin imports del proyecto (si no, la página no carga)", not propios,
      [ast.unparse(n) for n in propios])

titulo("2. el puente de la página reproduce reportes.py")
ns = {}
exec(AGREGACIONES.read_text(encoding="utf-8"), ns)
puente = re.search(r"const PUENTE = `(.*?)`;", APP_JS.read_text(encoding="utf-8"), re.S)
check("app.js trae el puente de Python", bool(puente))
exec(puente.group(1), ns)

for sem in [s for s in semestre.listar() if not s.startswith("_")]:
    local = reportes.panel(sem)
    if not local:
        continue
    meta = json.loads(ns["_cargar"](como_javascript(local)))
    ns["_filtrar"](json.dumps(meta["items"]), json.dumps(meta["grupos"]))
    esperado = reportes.filtrar([f for f in local if f.get("EnRoster")],
                                items=meta["items"], grupos=meta["grupos"])
    distintas = [fn for fn in FUNCIONES
                 if ns["_calc"](fn) != json.dumps(getattr(reportes, fn)(esperado), ensure_ascii=False)]
    check(f"{sem}: las {len(FUNCIONES)} funciones dan lo mismo", not distintas, distintas)
    fichas = [c for c in {f["Correo"] for f in esperado}
              if ns["_ficha"](c) != json.dumps(reportes.ficha(c, esperado), ensure_ascii=False)]
    check(f"{sem}: las fichas de alumno dan lo mismo", not fichas, fichas[:3])

titulo("3. el orden de las filas de entrada no cambia el resultado")
sem = [s for s in semestre.listar() if not s.startswith("_")][-1]
local = reportes.panel(sem)
meta = json.loads(ns["_cargar"](como_javascript(local)))
ns["_filtrar"]("[]", "[]")
a = ns["_calc"]("por_alumno")
ns["_cargar"](como_javascript(list(reversed(local))))
ns["_filtrar"]("[]", "[]")
check("por_alumno sale igual con las filas al revés", ns["_calc"]("por_alumno") == a)

titulo("4. al hacer clic, la lista tiene exactamente lo que cuenta la barra")
for sem in [s for s in semestre.listar() if not s.startswith("_")]:
    local = reportes.panel(sem)
    if not local:
        continue
    ns["_cargar"](como_javascript(local))
    ns["_filtrar"]("[]", "[]")
    lista = lambda **c: json.loads(ns["_casillas"](json.dumps(c)))
    dist = json.loads(ns["_calc"]("distribucion_notas"))
    malas = [d["Etiqueta"] for d in dist
             if len(lista(tramo=d["Tramo"], estado="evaluada")) != d["Alumnos"]]
    check(f"{sem}: cada tramo de nota abre tantos alumnos como dice su barra", not malas, malas)
    orig = json.loads(ns["_calc"]("distribucion_originalidad"))
    malas = [d["Originalidad"] for d in orig
             if len(lista(originalidad=d["Originalidad"])) != d["Evaluaciones"]]
    check(f"{sem}: cada categoría de originalidad abre lo que cuenta", not malas, malas)
    r = json.loads(ns["_calc"]("resumen"))
    check(f"{sem}: 'sin responder' abre {r['SinResponder']}",
          len(lista(estado="sin_responder")) == r["SinResponder"])
    check(f"{sem}: 'sin nota' abre {r['PendientesEvaluar']}",
          len(lista(estado="sin_nota")) == r["PendientesEvaluar"])
    check(f"{sem}: 'evaluadas' abre {r['Evaluados']}",
          len(lista(estado="evaluada")) == r["Evaluados"])
    semana_ok = all(len(lista(item=x["Item"])) == x["Casillas"]
                    for x in json.loads(ns["_calc"]("por_item")))
    check(f"{sem}: cada semana abre sus casillas", semana_ok)

titulo("5. el Worker devuelve las columnas en el orden de Python")
columnas_ts = re.search(r"const COLUMNAS = \[(.*?)\]", WORKER.read_text(encoding="utf-8"), re.S)
orden_ts = re.findall(r'"([A-Za-z]+)"', columnas_ts.group(1)) if columnas_ts else []
check("mismo orden que reportes.panel()", orden_ts == list(local[0].keys()),
      f"{orden_ts} vs {list(local[0].keys())}")

titulo("6. la página de datos guarda los CSV sin alterarlos")
# Abrir alumnos.csv o preguntas.csv en la página y guardarlo sin tocar nada
# tiene que dejar el archivo igual, byte a byte: mismo separador, mismos fines
# de línea, mismas comillas. Si no, cada guardado ensuciaría el historial.
if shutil.which("node"):
    editables = [p for s_ in semestre.listar() if not s_.startswith("_")
                 for p in (semestre.raiz(s_) / "alumnos.csv",
                           semestre.raiz(s_) / "tests_semanales" / "data" / "preguntas.csv",
                           semestre.raiz(s_) / "tareas" / "data" / "alumnos.csv") if p.exists()]
    csv_js = (RAIZ / "web" / "public" / "csv.js").resolve().as_uri()
    codigo = ("const { leerCsv, escribirCsv } = await import(process.argv[1]);"
              "const fs = await import('node:fs');"
              "for (const f of process.argv.slice(2)) {"
              "  const t = fs.readFileSync(f, 'utf8');"
              "  console.log(escribirCsv(leerCsv(t)) === t ? 'igual' : 'distinto', f); }")
    r = subprocess.run(["node", "--input-type=module", "-e", codigo, csv_js, *map(str, editables)],
                       capture_output=True, text=True, encoding="utf-8")
    distintos = [l for l in r.stdout.splitlines() if l.startswith("distinto")]
    check(f"{len(editables)} CSV editables quedan idénticos al guardarlos",
          r.returncode == 0 and editables and not distintos, (r.stderr or distintos)[:300])
    prueba = 'Nombre;Nota\r\n"Pérez; Ana";"6,5"\r\n"con ""comillas""\nen dos líneas";"7"\r\n'
    r = subprocess.run(["node", "--input-type=module", "-e",
                        "const m = await import(process.argv[1]); const d = m.leerCsv(process.argv[2]);"
                        "console.log(JSON.stringify([d.filas, m.escribirCsv(d) === process.argv[2]]))",
                        csv_js, prueba], capture_output=True, text=True, encoding="utf-8")
    filas, igual = json.loads(r.stdout) if r.returncode == 0 else ([], False)
    check("separador ;, comillas escapadas y saltos dentro de una celda",
          filas == [["Pérez; Ana", "6,5"], ['con "comillas"\nen dos líneas', "7"]] and igual, r.stdout[:300])
else:
    print("  (sin node en el PATH: no se prueba csv.js)")

titulo("7. el Worker, el motor y la página hablan de lo mismo")
from motor import trabajo  # noqa: E402

ts = WORKER.read_text(encoding="utf-8")
flujos_ts = set(re.findall(r'"([a-z]+\.[a-z]+)"', re.search(r"const FLUJOS = new Set\(\[(.*?)\]\)", ts, re.S).group(1)))
check("los flujos que acepta el Worker son los que ejecuta el motor",
      flujos_ts == set(trabajo.FLUJOS), f"{sorted(flujos_ts)} vs {sorted(trabajo.FLUJOS)}")
params_ts = set(re.findall(r"^  ([A-Z_]+): \(v\)", ts, re.M))
check("los parámetros que guarda el Worker son los que el motor pasa al script",
      params_ts == set(trabajo.PARAMETROS), f"{sorted(params_ts)} vs {sorted(trabajo.PARAMETROS)}")
datos_js = (RAIZ / "web" / "public" / "datos.js").read_text(encoding="utf-8")
defecto = dict(re.findall(r'([A-Z_]+): "([^"]*)"', re.search(r"const DEFECTO = \{(.*?)\};", datos_js, re.S).group(1)))
# La página muestra estos valores cuando nadie los cambió; tienen que ser los
# que config.py usa en ese caso. Se comparan como números cuando lo son.
# Se comparan con los valores por defecto escritos en config.py, no con los
# efectivos: el .env de quien corre la prueba puede haberlos cambiado.
fuente = (RAIZ / "modulos" / "config.py").read_text(encoding="utf-8")
en_config = dict(re.findall(r'(?:_env\.get|_flag)\("([A-Z_]+)", "([^"]*)"\)', fuente))
check("los valores por defecto de la página son los de config.py",
      set(defecto) == set(trabajo.PARAMETROS) and all(en_config.get(k) == v for k, v in defecto.items()),
      {k: (v, en_config.get(k)) for k, v in defecto.items() if en_config.get(k) != v})

titulo("7a. la página no muestra nodos como texto ('[object HTMLDivElement]')")
if shutil.which("node"):
    r = subprocess.run(["node", str(RAIZ / "web" / "scripts" / "probar-el.mjs")],
                       capture_output=True, text=True, encoding="utf-8")
    for linea in (r.stdout or "").splitlines():
        estado, _, nombre = linea.partition("\t")
        check(nombre, estado == "OK", linea)
    if r.returncode and not r.stdout:
        check("probar-el.mjs corre", False, r.stderr[-300:])

titulo("7a2. un correo en la salida de un trabajo se dibuja, no se ven sus etiquetas")
if shutil.which("node"):
    r = subprocess.run(["node", str(RAIZ / "web" / "scripts" / "probar-correos.mjs")],
                       capture_output=True, text=True, encoding="utf-8")
    for linea in (r.stdout or "").splitlines():
        estado, _, nombre = linea.partition("	")
        check(nombre, estado == "OK", linea)
    if r.returncode and not r.stdout:
        check("probar-correos.mjs corre", False, r.stderr[-300:])

titulo("7b. las rutas de archivos: nombres raros sí, salirse de la carpeta no")
if shutil.which("node"):
    r = subprocess.run(["node", str(RAIZ / "web" / "scripts" / "probar-rutas.mjs")],
                       capture_output=True, text=True, encoding="utf-8")
    for linea in (r.stdout or "").splitlines():
        estado, _, nombre = linea.partition("\t")
        check(nombre, estado == "OK", linea)
    if r.returncode and not r.stdout:
        check("probar-rutas.mjs corre", False, r.stderr[-300:])

titulo("7c. el editor de preguntas por semana escribe solo esa fila y muestra el correo real")
# Preguntas inventadas: el repo es público. Casos que rompen un CSV a mano:
# comas, comillas y saltos de línea dentro de una celda, una semana sin
# Tratamiento (se le manda lo de Control) y una fila en blanco al final.
if shutil.which("node"):
    import csv as _csv
    import io as _io
    import tempfile as _tempfile

    from modulos.tests import enviar as _enviar
    from modulos.tests.preguntas import _parsear_fila

    columnas = ["Semana", "Tema", "Fecha de Entrega"] + [
        f"{g} {'Pauta ' if pauta else ''}P{i}"
        for g in ("Control", "Tratamiento") for i in (1, 2, 3) for pauta in (False, True)]
    columnas = columnas[:3] + sorted(columnas[3:], key=lambda c: (c.split()[0] != "Control", "Pauta" in c, c[-1]))

    def _fila(semana, tema, fecha, control, tratamiento):
        f = {"Semana": semana, "Tema": tema, "Fecha de Entrega": fecha}
        for grupo, preguntas in (("Control", control), ("Tratamiento", tratamiento)):
            for i, (p, pauta) in enumerate(preguntas, 1):
                f[f"{grupo} P{i}"], f[f"{grupo} Pauta P{i}"] = p, pauta
        return f

    comun = ("¿Por qué se estima con una grilla, y no \"dentro\" de la verosimilitud?", "Por complejidad numérica.")
    filas = [
        _fila("1", "Regresión", "lunes 10/08, 10:15", [comun, ("Explique, con un ejemplo:\nla lealtad.", "Costos de cambio.")],
              [comun, ("¿Qué resuelve un logit anidado?", "Correlación dentro del nido.")]),
        _fila("2", "Sin grupos", "", [("Una sola pregunta.", "Una pauta.")], []),
        _fila("3", "Tres", "viernes", [("A", "a"), ("B", "b"), ("C", "c")], [("A", "a"), ("B", "b"), ("C", "c")]),
        _fila("", "", "", [], []),
    ]
    buf = _io.StringIO()
    escritor = _csv.DictWriter(buf, fieldnames=columnas, lineterminator="\n")
    escritor.writeheader()
    escritor.writerows([{c: f.get(c, "") for c in columnas} for f in filas])

    plantilla = ("<p>Hola {NOMBRE},</p><p>Videos de \"{TEMA}\". Entrega: <b>{FECHA_ENTREGA}</b>.</p>\n"
                 "  {BLOQUE_PREGUNTAS}\n<p>Módulo {SEMANA}</p>")
    correos = {}
    for f in filas[:3]:
        info = _parsear_fila({c: f.get(c, "") for c in columnas}, int(f["Semana"]))
        correos[f["Semana"]] = {g: _enviar._construir_cuerpo(plantilla, {"Nombre": "Ana Pérez", "Grupo": g}, info)
                                for g in ("control", "tratamiento")}
    esperado = {"plantilla": plantilla, "semanas": [1, 2, 3], "sin_tratamiento": [2], "correos": correos,
                "iguales": {"1": [True, False], "2": [True], "3": [True, True, True]}}

    with _tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "preguntas.csv").write_text(buf.getvalue(), encoding="utf-8", newline="")
        (Path(tmp) / "esperado.json").write_text(json.dumps(esperado, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run(["node", str(RAIZ / "web" / "scripts" / "probar-preguntas.mjs"),
                            str(Path(tmp) / "preguntas.csv"), str(Path(tmp) / "esperado.json")],
                           capture_output=True, text=True, encoding="utf-8")
    for linea in (r.stdout or "").splitlines():
        estado, _, nombre = linea.partition("\t")
        check(nombre, estado == "OK", linea)
    if r.returncode and not r.stdout:
        check("probar-preguntas.mjs corre", False, r.stderr[-300:])
else:
    print("  (sin node en el PATH: no se prueba preguntas.js)")

titulo("7d. la sábana se vuelve a armar sola cuando cambió algo de lo que lee")
if shutil.which("node"):
    r = subprocess.run(["node", str(RAIZ / "web" / "scripts" / "probar-sabana.mjs")],
                       capture_output=True, text=True, encoding="utf-8")
    for linea in (r.stdout or "").splitlines():
        estado, _, nombre = linea.partition("	")
        check(nombre, estado == "OK", linea)
    if r.returncode and not r.stdout:
        check("probar-sabana.mjs corre", False, r.stderr[-300:])

titulo("7d2. probar criterio: costo estimado, versiones por semana y comparación")
if shutil.which("node"):
    r = subprocess.run(["node", str(RAIZ / "web" / "scripts" / "probar-criterio.mjs")],
                       capture_output=True, text=True, encoding="utf-8")
    for linea in (r.stdout or "").splitlines():
        estado, _, nombre = linea.partition("	")
        if nombre:
            check(nombre, estado == "OK", linea)
    if r.returncode and not r.stdout:
        check("probar-criterio.mjs corre", False, r.stderr[-300:])

titulo("7d3. versiones anteriores de un prompt: cuáles hay, dónde se usó cada una y qué cambia")
# La huella la calcula el Python de verdad: si cambia cómo se normaliza el
# texto, la página dejaría de reconocer cuál es la versión vigente.
if shutil.which("node"):
    from modulos.ia import versiones as _versiones
    texto_prueba = "  Criterio de la semana\r\nNOTA FINAL: 1 a 7, ñandú\r\n\r\n"
    r = subprocess.run(["node", str(RAIZ / "web" / "scripts" / "probar-historial.mjs"),
                        texto_prueba, _versiones.huella(texto_prueba)],
                       capture_output=True, text=True, encoding="utf-8")
    for linea in (r.stdout or "").splitlines():
        estado, _, nombre = linea.partition("	")
        if nombre:
            check(nombre, estado == "OK", linea)
    # Si el script se cae a mitad de camino ya imprimió algunos OK: sin "todo OK" al final, falla.
    if r.returncode or "todo OK" not in r.stdout:
        check("probar-historial.mjs termina sin errores", False, r.stderr[-300:] or r.stdout[-300:])

titulo("7d4. traer precios: fuentes, búsqueda por nombre y filas que no se pisan")
# Sin red: las fuentes son copias recortadas dentro del script.
if shutil.which("node"):
    r = subprocess.run(["node", str(RAIZ / "web" / "scripts" / "probar-precios.mjs")],
                       capture_output=True, text=True, encoding="utf-8")
    for linea in (r.stdout or "").splitlines():
        estado, _, nombre = linea.partition("\t")
        if nombre:
            check(nombre, estado == "OK", linea)
    if r.returncode or "todo OK" not in r.stdout:
        check("probar-precios.mjs termina sin errores", False, r.stderr[-300:] or r.stdout[-300:])

titulo("7e. editar un prompt avisa antes de guardar algo que haría fallar un envío")
if shutil.which("node"):
    r = subprocess.run(["node", str(RAIZ / "web" / "scripts" / "probar-prompts.mjs")],
                       capture_output=True, text=True, encoding="utf-8")
    for linea in (r.stdout or "").splitlines():
        estado, _, nombre = linea.partition("	")
        check(nombre, estado == "OK", linea)
    if r.returncode and not r.stdout:
        check("probar-prompts.mjs corre", False, r.stderr[-300:])

titulo("7f. el gasto en la API, en qué va el curso y la barra de avance")
# La línea de consumo y las de avance las escribe el Python de verdad: si cambia
# su forma sin cambiar el lector de la página, el costo o la barra dejan de verse
# sin que nadie lo note.
if shutil.which("node"):
    import contextlib
    import io
    from modulos import ia as _ia
    from modulos.progreso import avanzar
    linea = _ia.linea_consumo("gpt-prueba", 2, 4900, 1250)
    avance = io.StringIO()
    with contextlib.redirect_stdout(avance):
        for _ in avanzar(["a", "b", "c"], "respuestas"):
            print("✓ una respuesta")
    r = subprocess.run(["node", str(RAIZ / "web" / "scripts" / "probar-consumo.mjs"), linea, avance.getvalue()],
                       capture_output=True, text=True, encoding="utf-8")
    for linea_salida in (r.stdout or "").splitlines():
        estado, _, nombre = linea_salida.partition("\t")
        check(nombre, estado == "OK", linea_salida)
    if r.returncode and not r.stdout:
        check("probar-consumo.mjs corre", False, r.stderr[-300:])

titulo("8. solo entra quien trae un token de Access firmado")
# El Worker no confía en el encabezado de correo: verifica la firma del token.
# Se prueba con claves generadas en el momento, sin red.
if shutil.which("node"):
    r = subprocess.run(["node", str(RAIZ / "web" / "scripts" / "probar-acceso.mjs")],
                       capture_output=True, text=True, encoding="utf-8")
    for linea in (r.stdout or "").splitlines():
        estado, _, nombre = linea.partition("	")
        check(nombre, estado == "OK", linea)
    if r.returncode and not r.stdout:
        check("probar-acceso.mjs corre", False, r.stderr[-300:])
else:
    print("  (sin node en el PATH: no se prueba acceso.ts)")

sys.exit(resultado())
