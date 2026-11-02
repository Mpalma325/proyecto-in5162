"""
Cada corrección anota con qué prompt, pauta y parámetros se hizo.

En 2026-2 el criterio de originalidad cambió entre las semanas 6 y 7 y no quedó
registrado: solo se notaba en las notas. Acá se prueba que la huella es estable
(no cambia por los fines de línea), que una versión nueva se guarda una sola
vez y que las huellas llegan a la metadata de la llamada.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import check, resultado, titulo  # noqa: E402

from modulos import ia  # noqa: E402
from modulos.ia import versiones  # noqa: E402
from modulos.tests import ia_prompts  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    prompts = Path(tmp) / "tests_semanales" / "prompts"
    prompts.mkdir(parents=True)
    ruta = prompts / "evaluar_respuesta.md"
    usados = prompts.parent / versiones.CARPETA

    titulo("1. la huella identifica el texto y la versión se guarda una vez")
    v1 = versiones.anotar(ruta, "Criterio A\npuntaje 0 a 3\n")
    check("archivo@huella", v1.startswith("evaluar_respuesta.md@") and len(v1.split("@")[1]) == 8, v1)
    check("guarda el texto de esa versión", (usados / f"evaluar_respuesta@{v1.split('@')[1]}.md").read_text(encoding="utf-8")
          == "Criterio A\npuntaje 0 a 3\n")
    check("los fines de línea de Windows no cambian la huella",
          versiones.anotar(ruta, "Criterio A\r\npuntaje 0 a 3\r\n") == v1)
    check("la misma versión no se guarda dos veces", len(list(usados.iterdir())) == 1)
    v_crlf = versiones.guardar(prompts.parent, "otro.md", "Uno\r\nDos\r\n")
    guardado = (usados / f"otro@{v_crlf.split('@')[1]}.md").read_bytes().decode("utf-8")
    check("un texto con \\r\\n se guarda tal cual y conserva la huella de su nombre",
          guardado == "Uno\r\nDos\r\n" and versiones.huella(guardado) == v_crlf.split("@")[1], repr(guardado))
    (usados / f"otro@{v_crlf.split('@')[1]}.md").unlink()
    v2 = versiones.anotar(ruta, "Criterio B (originalidad nueva)\npuntaje 0 a 3\n")
    check("un cambio en el prompt da otra huella y otro archivo", v2 != v1 and len(list(usados.iterdir())) == 2)

    titulo("2. la corrección anota prompt, pauta y parámetros")
    ruta.write_text("Evalúa {{PREGUNTAS}} con {{PAUTAS}}", encoding="utf-8")
    falsa = lambda *a, **k: ia.Respuesta("<p>NOTA FINAL: 6,0</p>",  # noqa: E731
                                         {"modelo": "m", "temperatura": 0.2, "max_tokens": 3000, "razonamiento": None})
    with patch.object(ia_prompts.config, "PROMPTS", prompts), patch.object(ia_prompts.ia, "completar", side_effect=falsa):
        texto = ia_prompts.evaluar_respuesta(["¿P?"], ["pauta"], "respuesta inventada")
        otra_pauta = ia_prompts.evaluar_respuesta(["¿P?"], ["pauta corregida"], "respuesta inventada")
        candidato = ia_prompts.evaluar_respuesta(["¿P?"], ["pauta"], "respuesta inventada", plantilla="otro {{PREGUNTAS}}")
    partes = texto.meta.get("versiones", "").split("; ")
    check("prompt del semestre, pauta y parámetros, en ese orden",
          len(partes) == 4 and partes[0] == versiones.anotar(ruta, "Evalúa {{PREGUNTAS}} con {{PAUTAS}}")
          and partes[1].startswith("pauta.md@") and partes[2:] == ["temperatura=0.2", "max_tokens=3000"], partes)
    guardada = usados / f"pauta@{partes[1].split('@')[1]}.md"
    check("la pauta con que se corrigió queda guardada para leerla después",
          guardada.exists() and "P1. pauta" in guardada.read_text(encoding="utf-8"))
    check("si la pauta cambia, cambia su huella",
          otra_pauta.meta["versiones"].split("; ")[1] != partes[1], otra_pauta.meta)
    check("un prompt candidato (Probar criterio) se marca como candidato",
          candidato.meta.get("versiones", "").startswith("candidato@"), candidato.meta)

sys.exit(resultado())
