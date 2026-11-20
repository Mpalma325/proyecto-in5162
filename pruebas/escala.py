"""
La escala de notas de los tests (modulos/escala.py): lineal, dos tramos, la
inversa, el redondeo y que la escala por defecto dé las mismas notas que el
prompt de siempre. No toca ningún semestre salvo una copia de la plantilla.
"""

import itertools
import json
import sys
from decimal import Decimal
from fractions import Fraction

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import check, resultado, semestre_desechable, titulo  # noqa: E402

from modulos import escala as E  # noqa: E402

titulo("1. lineal")
e = E.POR_DEFECTO
check("la de siempre es 4,0–7,0 con un decimal",
      (e.tipo, e.minima, e.maxima, e.decimales, e.puntaje_maximo_pregunta) == ("lineal", 4.0, 7.0, 1, 3))
check("logro 0 → mínima, 1 → máxima", e.nota(0) == Decimal("4.0") and e.nota(1) == Decimal("7.0"))
check("logro 5/6 → 6,5", e.texto(e.nota(Fraction(5, 6))) == "6,5", e.nota(Fraction(5, 6)))
cien = E.Escala(minima=0, maxima=100, decimales=0)
check("0–100 sin decimales: 0,83 → 83", cien.texto(cien.nota("0,83")) == "83")
dos = E.Escala(minima=1, maxima=7, decimales=2)
check("dos decimales se escriben con los dos: 1/2 → 4,00", dos.texto(dos.nota(0.5)) == "4,00")
for malo in (-0.1, 1.2):
    try:
        e.nota(malo)
        check(f"logro {malo} se rechaza", False)
    except ValueError:
        check(f"logro {malo} se rechaza", True)

titulo("2. dos tramos (la escala del 60 %)")
t = E.Escala(tipo="dos_tramos", minima=1.0, maxima=7.0, aprobacion=4.0, exigencia=0.6)
check("0 → 1,0", t.texto(t.nota(0)) == "1,0")
check("60 % → 4,0 justo", t.texto(t.nota(0.6)) == "4,0")
check("30 % → 2,5 (bajo la exigencia)", t.texto(t.nota(0.3)) == "2,5")
check("80 % → 5,5 (sobre la exigencia)", t.texto(t.nota(0.8)) == "5,5")
check("100 % → 7,0", t.texto(t.nota(1)) == "7,0")
check("se describe en una línea", t.describir() == "1-7/1 4 al 60 %" and e.describir() == "4-7/1",
      (t.describir(), e.describir()))

titulo("3. la inversa")
check("lineal: 6,5 → 5/6", e.logro("6,5") == Fraction(5, 6))
check("dos tramos: 4,0 → 0,6 y 5,5 → 0,8", t.logro("4,0") == Fraction(3, 5) and t.logro(5.5) == Fraction(4, 5))
check("dos tramos: 2,5 → 0,3", t.logro("2,5") == Fraction(3, 10))
check("fuera de la escala no tiene logro (un 3,0 en 4–7)", e.logro("3,0") is None and e.logro("7,1") is None)
ida_y_vuelta = [x / 20 for x in range(21)]
check("ida y vuelta exacta en las dos escalas",
      all(esc.logro(esc.nota_exacta(x)) == Fraction(repr(x)) for esc in (e, t) for x in ida_y_vuelta))
check("el logro se guarda con cuatro decimales", E.texto_logro(Fraction(5, 6)) == "0.8333")

titulo("4. redondeo hacia arriba en el medio, no al par")
check("6,25 → 6,3 (round() de Python daría 6,2)", e.texto(Decimal("6.25")) == "6,3" and round(6.25, 1) == 6.2)
check("4,25 → 4,3 y 4,15 → 4,2", e.texto("4,25") == "4,3" and e.texto("4.15") == "4,2")
check("5,05 → 5,1 aunque el float 5.05 sea 5,04999…", e.texto(5.05) == "5,1")
check("0 decimales: 82,5 → 83", cien.texto("82.5") == "83")

titulo("5. la escala por defecto da lo que pedía el prompt de siempre")
# El prompt viejo: cada pregunta de 0 a 3 (0; 0,5; 1; 2; 3), se le suma 4 y se
# promedia. Con 1, 2 o 3 preguntas, todas las combinaciones posibles.
RUBRICA = (Fraction(0), Fraction(1, 2), Fraction(1), Fraction(2), Fraction(3))
distintas = []
for n in (1, 2, 3):
    for p in itertools.product(RUBRICA, repeat=n):
        prompt = sum(x + 4 for x in p) / n  # nota de cada pregunta, promediada
        esperada = e.redondear(prompt)
        logro = e.logro_de(p)
        if e.nota(logro) != esperada:
            distintas.append((p, e.nota(logro), esperada))
check("todas las combinaciones de 1 a 3 preguntas dan la misma nota", not distintas, distintas[:3])
check("logro_de usa el máximo de 3 por pregunta", e.logro_de([3, 2]) == Fraction(5, 6))
try:
    e.logro_de([4])
    check("un puntaje sobre el máximo se rechaza", False)
except ValueError:
    check("un puntaje sobre el máximo se rechaza", True)

titulo("6. validación")
for nombre, datos in (("mínima mayor que la máxima", {"minima": 7, "maxima": 4}),
                      ("tres decimales", {"decimales": 3}),
                      ("máxima sobre 1000", {"maxima": 1001}),
                      ("dos tramos sin exigencia", {"tipo": "dos_tramos", "aprobacion": 4, "minima": 1}),
                      ("aprobación fuera de rango", {"tipo": "dos_tramos", "minima": 1, "aprobacion": 8,
                                                     "exigencia": 0.6}),
                      ("exigencia de 1", {"tipo": "dos_tramos", "minima": 1, "aprobacion": 4, "exigencia": 1}),
                      ("tipo desconocido", {"tipo": "curva"}),
                      ("clave desconocida", {"minimo": 1})):
    try:
        E.desde_dict(datos)
        check(f"rechaza: {nombre}", False)
    except ValueError:
        check(f"rechaza: {nombre}", True)
check("las claves que faltan toman el valor por defecto", E.desde_dict({"minima": 1}).maxima == 7.0)

titulo("7. leer la del semestre")
with semestre_desechable(base="_template", sid="_tmp_escala") as (sid, tmp):
    from modulos import escala as E2

    check("sin escala_notas.json rige la de siempre", E2.leer(sid) == E2.POR_DEFECTO)
    (tmp / E2.ARCHIVO).write_text(json.dumps({"tipo": "lineal", "minima": 1.0, "maxima": 7.0,
                                              "decimales": 1, "aprobacion": None, "exigencia": None,
                                              "puntaje_maximo_pregunta": 3}), encoding="utf-8")
    leida = E2.leer(sid)
    check("con el archivo, la del archivo", leida.minima == 1.0 and leida.texto(leida.nota(0.5)) == "4,0")
    (tmp / E2.ARCHIVO).write_text("{no es json", encoding="utf-8")
    try:
        E2.leer(sid)
        check("un archivo roto es un error claro", False)
    except ValueError as err:
        check("un archivo roto es un error claro", "escala_notas.json" in str(err), str(err))


def _correr(escala: dict, *extra) -> tuple[int, str, dict]:
    """El trabajo datos.escala como lo llama el motor; devuelve (código, salida, lo de la línea @@escala)."""
    import contextlib
    import io

    from modulos.datos import escala_trabajo
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        codigo = escala_trabajo.main(["--escala", json.dumps(escala), "--por", "profe@x.cl", *extra])
    texto = salida.getvalue()
    marca = next((json.loads(l.split(" ", 1)[1]) for l in texto.splitlines() if l.startswith("@@escala ")), {})
    return codigo, texto, marca


def _huella(p) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "(no existe)"


UNO_A_SIETE = {"tipo": "lineal", "minima": 1.0, "maxima": 7.0, "decimales": 1, "aprobacion": None,
               "exigencia": None, "puntaje_maximo_pregunta": 3}
DEL_60 = {**UNO_A_SIETE, "tipo": "dos_tramos", "aprobacion": 4.0, "exigencia": 0.6}

titulo("8. cambiar la escala: simulación y recálculo (datos.escala)")
with semestre_desechable(base="_template", sid="_tmp_escala_recalculo") as (sid, tmp):
    from modulos.datos import TAREAS, TESTS, _csv
    from modulos.datos import log as L
    from modulos.datos import notas as N
    from modulos.datos.esquema import COLUMNAS_NOTAS, NOTAS
    from modulos import escala as E3

    def fila(correo, nota, logro="", flujo=TESTS, item="1", **resto):
        return {**{c: "" for c in COLUMNAS_NOTAS}, "Correo": correo, "Flujo": flujo, "Item": item,
                "Enviado": "2026-11-01T10:00:00-03:00", "Nota": nota, "Logro": logro, **resto}

    _csv.escribir(NOTAS, [
        fila("a@x.cl", "6,5"),                          # corrección de antes, sin puntajes ni logro
        fila("b@x.cl", "7,0", "1.0000"),                # puntajes 3;3, se mantiene en 7,0
        fila("c@x.cl", "3,0"),                          # ajuste bajo la mínima: fijo
        fila("d@x.cl", "", Corregido="2026-11-02T10:00:00-03:00"),  # por revisar: sin nota
        fila("e@x.cl", "5.5", flujo=TAREAS, item="T1"),  # tareas: no se toca
        fila("f@x.cl", "5,5", "0.5000"),                # puntajes 2;1
        fila("g@x.cl", "5,0", "0.3333"),                # ajuste avisado por correo
    ], COLUMNAS_NOTAS, sid)
    L.registrar("evaluacion", TESTS, "1", "a@x.cl", sid, Nota="6,5",
                EvaluacionIA="<p><b>NOTA FINAL:</b> 6,5</p>")
    L.registrar("evaluacion", TESTS, "1", "b@x.cl", sid, Nota="7,0", Puntajes="3;3", Logro="1.0000",
                EvaluacionIA="<p><b>EVALUACIÓN:</b> 3 / 3 puntos</p>")
    L.registrar("evaluacion", TESTS, "1", "c@x.cl", sid, Nota="5,0", EvaluacionIA="<p>NOTA FINAL: 5,0</p>")
    L.registrar("ajuste", TESTS, "1", "c@x.cl", sid, Nota="3,0", Logro="", Detalle="copia (antes: 5,0; por profe)")
    L.registrar("evaluacion", TESTS, "1", "f@x.cl", sid, Nota="5,5", Puntajes="2;1", Logro="0.5000",
                EvaluacionIA="<p><b>NOTA FINAL:</b> 5,5</p>")
    L.registrar("evaluacion", TESTS, "1", "g@x.cl", sid, Nota="6,0", Puntajes="3;1", Logro="0.6667",
                EvaluacionIA="<p><b>EVALUACIÓN:</b> 3 / 3 puntos</p>")
    L.registrar("ajuste", TESTS, "1", "g@x.cl", sid, Nota="5,0", Logro="0.3333", MessageId="<aviso@x>",
                Detalle="revisión (antes: 6,0; por profe)")

    notas_csv, log_csv, archivo = tmp / NOTAS, tmp / "log_envios.csv", tmp / E3.ARCHIVO
    antes = (_huella(notas_csv), _huella(log_csv), _huella(archivo))
    codigo, salida, marca = _correr(UNO_A_SIETE, "--dry-run")
    salida_simulacion = salida
    check("la simulación termina bien", codigo == 0, salida)
    check("no escribe nada: ni notas.csv, ni el log, ni escala_notas.json",
          (_huella(notas_csv), _huella(log_csv), _huella(archivo)) == antes)
    check("cuenta las notas de Tests: 5 (la por revisar no tiene), cambian 3, una fija",
          (marca.get("notas"), marca.get("cambian"), marca.get("fijas")) == (5, 3, 1), marca)
    check("las tres que cambian ya las vio el alumno con número (NOTA FINAL o aviso del ajuste)",
          marca.get("comunicadas") == 3, marca)
    check("media antes y después: 5,40 → 4,60", (marca.get("media_antes"), marca.get("media_despues")) == ("5,40", "4,60"), marca)
    check("dice el mayor cambio", "Mayor cambio: g@x.cl · test 1: 5,0 → 3,0 (−2,00)" in salida, salida)
    check("lista la fija con el motivo", "⊘ c@x.cl · test 1: 3,0 queda fija (ajuste fuera de la escala)" in salida,
          salida)
    check("la marca trae la escala propuesta", marca.get("escala") == UNO_A_SIETE, marca.get("escala"))

    codigo, salida, marca = _correr(UNO_A_SIETE)
    estado = {(f["Correo"], f["Flujo"]): f for f in _csv.leer(NOTAS, sid)}
    check("en real escribe escala_notas.json", codigo == 0 and E3.leer(sid) == E3.desde_dict(UNO_A_SIETE), salida)
    check("recalcula: 6,5 → 6,0 (de la inversa), 5,5 → 4,0 (de los puntajes), 5,0 → 3,0 (ajuste con logro)",
          [estado[(c, TESTS)]["Nota"] for c in ("a@x.cl", "f@x.cl", "g@x.cl")] == ["6,0", "4,0", "3,0"],
          [estado[(c, TESTS)]["Nota"] for c in ("a@x.cl", "f@x.cl", "g@x.cl")])
    check("y escribe su logro", estado[("a@x.cl", TESTS)]["Logro"] == "0.8333", estado[("a@x.cl", TESTS)])
    check("el ajuste bajo la mínima queda igual, sin logro",
          (estado[("c@x.cl", TESTS)]["Nota"], estado[("c@x.cl", TESTS)]["Logro"]) == ("3,0", ""))
    check("7,0 sigue en 7,0; la por revisar sigue sin nota; Tareas no se toca",
          (estado[("b@x.cl", TESTS)]["Nota"], estado[("d@x.cl", TESTS)]["Nota"],
           estado[("e@x.cl", TAREAS)]["Nota"]) == ("7,0", "", "5.5"))
    recalculos = L.leer(sid, evento="recalculo")
    check("un evento recalculo por nota que cambió", sorted(e["Correo"] for e in recalculos)
          == ["a@x.cl", "f@x.cl", "g@x.cl"], recalculos)
    check("con la nota, el logro y qué escala cambió por cuál, y quién",
          all(e["Detalle"] == "escala 4-7/1 → 1-7/1; por profe@x.cl" for e in recalculos)
          and next(e for e in recalculos if e["Correo"] == "a@x.cl")["Nota"] == "6,0", recalculos)
    check("reconstruir desde el log da la nota recalculada",
          L.reconstruir_estado(sid)[("a@x.cl", TESTS, "1")]["Nota"] == "6,0")
    check("y sincronizar no la vuelve atrás", N.sincronizar_desde_log(sid, simular=True)["NotaAlDia"] == 0)

    titulo("9. de 1–7 a la del 60 %: el logro exacto, no el de cuatro decimales")
    codigo, salida, marca = _correr(DEL_60)
    estado = {f["Correo"]: f for f in _csv.leer(NOTAS, sid) if f["Flujo"] == TESTS}
    # a: 6,0 en 1–7 es 5/6 exacto → 4 + 3 × (5/6 − 0,6) / 0,4 = 5,75 → 5,8.
    # Con el Logro guardado (0.8333) daría 5,749… → 5,7.
    check("6,0 (logro 5/6) → 5,8: 5,75 redondea hacia arriba", estado["a@x.cl"]["Nota"] == "5,8", estado["a@x.cl"])
    check("puntajes 2;1 (logro 1/2) → 3,5, bajo la exigencia", estado["f@x.cl"]["Nota"] == "3,5", estado["f@x.cl"])
    check("el ajuste fijo sigue fijo aunque ahora 3,0 caiga dentro de la escala",
          estado["c@x.cl"]["Nota"] == "3,0" and marca.get("fijas") == 1, (estado["c@x.cl"], marca))
    check("el detalle describe la escala de dos tramos",
          L.leer(sid, evento="recalculo")[-1]["Detalle"] == "escala 1-7/1 → 1-7/1 4 al 60 %; por profe@x.cl")

titulo("10. el empate: 0,5 y 0 puntos de 4–7 con dos decimales a 4–7 con uno")
with semestre_desechable(base="_template", sid="_tmp_escala_empate") as (sid, tmp):
    from modulos.datos import TESTS, _csv
    from modulos.datos import log as L
    from modulos.datos.esquema import COLUMNAS_NOTAS, NOTAS
    from modulos import escala as E3

    (tmp / E3.ARCHIVO).write_text(json.dumps({"minima": 4, "maxima": 7, "decimales": 2}), encoding="utf-8")
    vacia = {c: "" for c in COLUMNAS_NOTAS}
    _csv.escribir(NOTAS, [
        {**vacia, "Correo": "h@x.cl", "Flujo": TESTS, "Item": "2", "Nota": "4,25", "Logro": "0.0833"},
        {**vacia, "Correo": "i@x.cl", "Flujo": TESTS, "Item": "2", "Nota": "4,25", "Logro": "0.0833"},
    ], COLUMNAS_NOTAS, sid)
    L.registrar("evaluacion", TESTS, "2", "h@x.cl", sid, Nota="4,25", Puntajes="0.5;0", Logro="0.0833")
    L.registrar("evaluacion", TESTS, "2", "i@x.cl", sid, Nota="4,25", Logro="0.0833")
    codigo, salida, marca = _correr({**E3.POR_DEFECTO.como_dict()})
    estado = {f["Correo"]: f["Nota"] for f in _csv.leer(NOTAS, sid)}
    check("desde los puntajes (1/12 exacto): 4,25 → 4,3", estado["h@x.cl"] == "4,3", (estado, salida))
    check("sin puntajes, desde la inversa exacta de 4,25: también 4,3 (con 0.0833 sería 4,2)",
          estado["i@x.cl"] == "4,3", estado)

titulo("11. la página: «Guardar y recalcular» con la simulación de verdad (Node)")
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402


def _js(llamadas: list[dict]) -> list:
    raiz = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "llamadas.json"
        ruta.write_text(json.dumps(llamadas, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run(["node", str(raiz / "web" / "scripts" / "probar-correccion.mjs"), str(ruta)],
                           capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(r.stderr[-600:])
    return [x.get("ok", x) for x in json.loads(r.stdout)]


if not shutil.which("node"):
    print("  (sin node en el PATH: no se prueba la confirmación de la página)")
else:
    sin_comunicadas = {**marca, "comunicadas": 0}
    formulario = {"conAprobacion": False, "minima": "1,0", "maxima": "7", "decimales": "1", "aprobacion": "4",
                  "exigencia": "60", "puntajeMaximo": 3}
    resumen, confirmacion, sin_id, bien, mal, leida, del_60, mala, visible = _js([
        {"f": "escala.resumenSimulacion", "args": [salida_simulacion]},
        {"f": "escala.confirmacionEscala", "args": [{"cambian": 3, "fijas": 1, "comunicadas": 3,
                                                    "media_antes": "5,40", "media_despues": "4,60"}, "2026-3"]},
        {"f": "escala.confirmacionEscala", "args": [sin_comunicadas, "2026-3"]},
        {"f": "escala.idConfirmado", "args": [" 2026-3 ", "2026-3"]},
        {"f": "escala.idConfirmado", "args": ["2026-2", "2026-3"]},
        {"f": "escala.escalaDelFormulario", "args": [formulario]},
        {"f": "escala.escalaDelFormulario", "args": [{**formulario, "conAprobacion": True, "aprobacion": "4,0"}]},
        {"f": "escala.escalaDelFormulario", "args": [{**formulario, "minima": "8"}]},
        {"f": "comun.sinProgreso", "args": [salida_simulacion]},
    ])
    check("la página lee el resumen que dejó la simulación", resumen is not None and resumen["comunicadas"] == 3
          and resumen["escala"] == UNO_A_SIETE, resumen)
    check("con notas ya comunicadas, la confirmación pide escribir el id del semestre",
          confirmacion["pideId"] and "3 notas que cambian ya les llegaron por correo" in confirmacion["texto"]
          and "escribe 2026-3" in confirmacion["texto"], confirmacion)
    check("y dice cuántas cambian, las fijas y la media", all(x in confirmacion["texto"] for x in
                                                              ("cambian 3 notas", "1 queda fija", "5,40 a 4,60")),
          confirmacion["texto"])
    check("sin notas comunicadas basta con confirmar", sin_id["pideId"] is False, sin_id)
    check("el id se compara tal cual (sin espacios a los lados)", bien is True and mal is False)
    check("el formulario arma la misma escala que se simuló (1,0 con coma)",
          leida["error"] == "" and _js([{"f": "escala.mismaEscala", "args": [leida["escala"], resumen["escala"]]}])[0],
          leida)
    check("la de dos tramos sale de la casilla, con la exigencia en %",
          del_60["escala"]["tipo"] == "dos_tramos" and del_60["escala"]["exigencia"] == 0.6, del_60)
    check("una mínima sobre la máxima se dice en el formulario", mala["escala"] is None and "mínima" in mala["error"],
          mala)
    check("la línea @@escala no se muestra en la salida", "@@escala" not in visible and "Mayor cambio" in visible)

sys.exit(resultado())
