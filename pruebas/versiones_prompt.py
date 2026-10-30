"""
Cada corrección anota con qué versión del prompt se hizo.

En 2026-2 el criterio de originalidad cambió entre las semanas 6 y 7 y no quedó
registrado: solo se notaba en las notas. Acá se prueba que la huella es estable
(no cambia por los fines de línea), que una versión nueva se guarda una sola
vez y que la huella llega a la metadata de la llamada.
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
    v2 = versiones.anotar(ruta, "Criterio B (originalidad nueva)\npuntaje 0 a 3\n")
    check("un cambio en el prompt da otra huella y otro archivo", v2 != v1 and len(list(usados.iterdir())) == 2)

    titulo("2. la llamada de corrección lleva la versión en su metadata")
    ruta.write_text("Evalúa {{PREGUNTAS}} con {{PAUTAS}}", encoding="utf-8")
    falsa = lambda *a, **k: ia.Respuesta("<p>NOTA FINAL: 6,0</p>", {"modelo": "m"})  # noqa: E731
    with patch.object(ia_prompts.config, "PROMPTS", prompts), patch.object(ia_prompts.ia, "completar", side_effect=falsa):
        texto = ia_prompts.evaluar_respuesta(["¿P?"], ["pauta"], "respuesta inventada")
        candidato = ia_prompts.evaluar_respuesta(["¿P?"], ["pauta"], "respuesta inventada", plantilla="otro {{PREGUNTAS}}")
    check("evaluación con el prompt del semestre", texto.meta.get("prompt") ==
          versiones.anotar(ruta, "Evalúa {{PREGUNTAS}} con {{PAUTAS}}"), texto.meta)
    check("un prompt candidato (Probar criterio) se marca como candidato",
          candidato.meta.get("prompt", "").startswith("candidato@"), candidato.meta)

sys.exit(resultado())
