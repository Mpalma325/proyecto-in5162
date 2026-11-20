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

sys.exit(resultado())
