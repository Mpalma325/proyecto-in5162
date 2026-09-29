"""
El contexto del curso que ve el modelo al generar las preguntas de tareas.

En 2026-2 la carpeta de clases quedó vacía y la T1 se generó sin contexto, sin
que nada lo avisara. Esto prueba que el contexto se arma con cualquier tipo de
material, que se actualiza al cambiar una clase y que la falta se nota.
"""

import sys

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import check, resultado, semestre_desechable, titulo  # noqa: E402

CLASE_R = ('<html><body><p>Intro</p><pre class="sourceCode r"><code class="sourceCode r">'
           '<span class="fu">lm</span>(y ~ x, data = d)</code></pre></body></html>')
CLASE_SIN_R = "<html><body><h1>Clase 3</h1><p>El modelo logit y sus supuestos.</p></body></html>"

with semestre_desechable(sid="_tmp_contexto") as (sid, tmp):
    from modulos.tareas import config, contexto

    carpeta = config.CLASES
    carpeta.mkdir(parents=True, exist_ok=True)
    for p in carpeta.iterdir():
        if p.is_file():
            p.unlink()

    titulo("1. sin material, se avisa")
    r = contexto.resumen()
    check("no hay archivos", r["activo"] and r["archivos"] == [], r)
    check("el aviso lo dice claro", "no hay ninguno" in contexto.describir(r))
    check("y el modelo no recibe nada", contexto.cargar() == "")

    titulo("2. cada tipo de archivo aporta lo suyo")
    (carpeta / "S01-regresion.html").write_text(CLASE_R, encoding="utf-8")
    (carpeta / "S03-logit.html").write_text(CLASE_SIN_R, encoding="utf-8")
    (carpeta / "apuntes.md").write_text("# Apuntes\nUsar siempre tidyverse.", encoding="utf-8")
    (carpeta / "notas.pdf").write_bytes(b"%PDF no se usa")
    texto = contexto.cargar()
    check("de la clase de RMarkdown, el código R", "lm(y ~ x, data = d)" in texto and "Intro" not in texto, texto)
    check("de un HTML sin código, el texto", "modelo logit y sus supuestos" in texto, texto)
    check("un apunte en markdown, tal cual", "Usar siempre tidyverse." in texto)
    check("lo que no es de un formato admitido no entra", "PDF" not in texto)
    check("el resumen cuenta 3 archivos", len(contexto.resumen()["archivos"]) == 3, contexto.resumen())

    titulo("3. al cambiar una clase, se usa la versión nueva")
    (carpeta / "S01-regresion.html").write_text(CLASE_R.replace(">lm<", ">glm<"), encoding="utf-8")
    texto = contexto.cargar()
    check("el modelo ve el código nuevo", "glm(y ~ x" in texto, texto[:200])
    check("y no el viejo", "\nlm(y ~ x" not in texto and not texto.startswith("lm("), texto[:200])

    titulo("4. un archivo gigante no se lleva todo el contexto")
    (carpeta / "enorme.txt").write_text("x" * 100_000, encoding="utf-8")
    enorme = next(a for a in contexto.resumen()["archivos"] if a["nombre"] == "enorme.txt")
    check("se corta en el tope", enorme["caracteres"] == contexto.MAX_CARACTERES, enorme)

sys.exit(resultado())
