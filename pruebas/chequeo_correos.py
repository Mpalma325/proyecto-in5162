"""
El chequeo de Tareas con entregas de verdad: lo que antes se arreglaba a mano.

- Un integrante que no calzó con la lista de alumnos, y su correo elegido en
  el chequeo (correos_<T>.csv), que después usa generar.
- Un alumno que aparece en dos entregas: se avisa y recibe una sola pregunta.
- Un .rar subido sin abrir: el chequeo lo abre y su HTML pasa a ser una entrega.

No hay red ni API: el chequeo no llama al modelo, y generar se prueba con el
modelo reemplazado.
"""

import csv
import sys
from unittest.mock import patch

sys.path.insert(0, "pruebas")
from comun import check, resultado, semestre_desechable, titulo  # noqa: E402
from entregas_zip import _rar  # noqa: E402

RELLENO = "<p>" + "Se estima el modelo con lm() sobre las ventas por semana. " * 50 + "</p>"


def entrega(autores: str) -> bytes:
    """Una entrega sin tabla de roles: los integrantes salen del encabezado."""
    cuerpo = "".join(f"<p>### Pregunta {n}</p>{RELLENO}<pre><code>modelo_{n} &lt;- lm(y ~ x)</code></pre>"
                     for n in (1, 2, 3, 4))
    return (f'<html><head><title>T9</title></head><body><h4 class="author">{autores}</h4>'
            f"{cuerpo}</body></html>").encode()


with semestre_desechable(base="_template", sid="_tmp_chequeo_correos") as (sid, tmp):
    with (tmp / "alumnos.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Nombre", "Correo", "Grupo"])
        for nombre, correo in (("Ana María Pérez Soto", "ana@x.cl"), ("Bruno Díaz Lagos", "bruno@x.cl"),
                               ("Carla Rojas Mena", "carla@x.cl"), ("Daniel Fuentes Vera", "daniel@x.cl")):
            w.writerow([nombre, correo, ""])
    carpeta = tmp / "tareas" / "data" / "entregas" / "T9"
    carpeta.mkdir(parents=True)
    (carpeta / "T9-Grupo1.html").write_bytes(entrega("Ana María Pérez Soto, Bruno Díaz Lagos, Xiomara Q"))
    # Bruno subió además su propia versión (pasó en T2 de 2026-2).
    (carpeta / "T9-Bruno.html").write_bytes(entrega("Bruno Díaz Lagos"))
    (carpeta / "T9-Grupo3.rar").write_bytes(_rar({"tarea/informe.html": entrega("Carla Rojas Mena, Daniel Fuentes Vera")}))

    from modulos.tareas import asignacion, chequeo, generar, storage

    titulo("1. el chequeo abre los .rar y avisa lo que hay que resolver")
    informe = chequeo.revisar("T9")
    archivos = [g["archivo"] for g in informe["grupos"]]
    check("el .rar se abre y su HTML entra al chequeo",
          informe["desempacados"] == ["T9-Grupo3.html"] and "T9-Grupo3.html" in archivos, (informe["desempacados"], archivos))
    grupo1 = next(g for g in informe["grupos"] if g["archivo"] == "T9-Grupo1.html")
    xiomara = next(i for i in grupo1["integrantes"] if i["nombre"] == "Xiomara Q")
    check("quien no calza con la lista queda sin correo, para elegirlo",
          not grupo1["bloqueo"] and xiomara["correo"] == "" and not xiomara["correo_a_mano"], grupo1)
    check("el que aparece en dos entregas se avisa",
          [(d["correo"], d["archivos"]) for d in informe["duplicados"]]
          == [("bruno@x.cl", ["T9-Bruno.html", "T9-Grupo1.html"])], informe["duplicados"])

    titulo("2. el correo elegido a mano se ve en el chequeo y lo usa generar")
    asignacion.escribir_correos("T9", {("T9-Grupo1.html", "Xiomara Q"): "daniel@x.cl"})
    informe = chequeo.revisar("T9")
    check("un .rar ya abierto no se vuelve a abrir", informe["desempacados"] == [], informe["desempacados"])
    grupo1 = next(g for g in informe["grupos"] if g["archivo"] == "T9-Grupo1.html")
    xiomara = next(i for i in grupo1["integrantes"] if i["nombre"] == "Xiomara Q")
    check("el chequeo muestra el correo elegido a mano",
          xiomara["correo"] == "daniel@x.cl" and xiomara["correo_a_mano"], xiomara)
    # Elegir el correo de alguien que está en otra entrega también se avisa.
    check("un correo elegido a mano que ya estaba en otra entrega se avisa",
          ("daniel@x.cl", ["T9-Grupo1.html", "T9-Grupo3.html"])
          in [(d["correo"], d["archivos"]) for d in informe["duplicados"]], informe["duplicados"])

    def _preguntas(secciones, roles_html, asignacion):
        """El modelo, reemplazado: una pregunta por integrante, en la parte asignada."""
        return {"integrantes": [{"nombre": n, "pregunta_tarea": parte, "pregunta": "¿Qué hace modelo_1?",
                                 "pauta": "Explica lm().", "motivo_sin_pregunta": None}
                                for n, parte in (asignacion or {}).items()]}

    with patch.object(generar, "generar_preguntas", side_effect=_preguntas):
        generar.main("T9", sorted(carpeta.glob("*.html")), interactivo=False)
    filas = storage.leer_csv("T9")
    por_nombre = {}
    for f in filas:
        por_nombre.setdefault(f["alumno_nombre"], []).append(f)
    check("generar usa el correo elegido a mano",
          [f["alumno_correo"] for f in por_nombre.get("Xiomara Q", [])] == ["daniel@x.cl"], por_nombre.get("Xiomara Q"))
    correos = [f["alumno_correo"] for f in filas if f["alumno_correo"]]
    check("nadie queda con dos preguntas", len(correos) == len(set(correos)), sorted(correos))

sys.exit(resultado())
