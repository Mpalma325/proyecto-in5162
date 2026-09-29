"""
Lo que llega de U-Cursos y lo que queda en entregas/.

La descarga de U-Cursos es un zip con un comprimido por alumno adentro, y cada
uno trae el HTML renderizado, el .Rmd, los datos y basura de macOS. Estas
pruebas arman esa forma y comprueban que salgan solo las entregas, con nombres
que no se pisen entre grupos.

No hay red ni API acá: es todo desempaquetado.
"""

import shutil
import sys
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

sys.path.insert(0, ".")

from pruebas.comun import check, resultado  # noqa: E402
# "app" solo, sin importarlo como paquete: si hay otro paquete "app" instalado
# en el Python (pasa con proyectos en modo editable), le ganaría a esta carpeta.
sys.path.insert(0, "app")
from utils import runner  # noqa: E402


class _Subido:
    """Un archivo como lo entrega el file_uploader de Streamlit."""

    def __init__(self, nombre: str, contenido: bytes):
        self.name = nombre
        self._contenido = contenido

    def getvalue(self) -> bytes:
        return self._contenido


def _zip_de_grupo(html: bytes, rmd: bytes | None, carpeta: str) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{carpeta}/Tarea01---IN5162Prim26.html", html)
        if rmd is not None:
            zf.writestr(f"{carpeta}/Tarea01 - IN5162Prim26.Rmd", rmd)
        zf.writestr(f"{carpeta}/myBD_rendimiento.csv", b"a,b\n1,2\n")
        zf.writestr(f"__MACOSX/{carpeta}/._Tarea01---IN5162Prim26.html", b"basura")
    return buf.getvalue()


def _zip_de_ucursos(grupos: dict) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for nombre, contenido in grupos.items():
            zf.writestr(nombre, contenido)
    return buf.getvalue()


def main() -> int:
    grupos = {
        "Soto_Rojas__Bruno_11111111.zip":
            _zip_de_grupo(b"<html>soto</html>", b"---\nauthor: Bruno Soto\n---\n", "t1-Soto"),
        "Mora_Vidal__Ana_22222222.zip":
            _zip_de_grupo(b"<html>mora</html>", None, "t1-Mora-Vidal"),
    }
    subido = _Subido("Tarea 1.zip", _zip_de_ucursos(grupos))

    with tempfile.TemporaryDirectory() as tmp:
        destino = Path(tmp) / "T1"
        agregados, omitidos = runner.extraer_entregas([subido], destino)

        htmls = sorted(p.name for p in destino.glob("*.html"))
        rmds = sorted(p.name for p in destino.glob("*.Rmd"))

        check("sale un HTML por grupo", len(htmls) == 2, htmls)
        # Los dos grupos entregan un HTML con el mismo nombre; si no se
        # prefijaran, el segundo pisaría al primero y se perdería un grupo.
        check("los HTML no se pisan entre grupos", len(set(htmls)) == 2, htmls)
        check("el HTML lleva el nombre del grupo",
              all(h.startswith(("Soto", "Mora")) for h in htmls), htmls)
        check("el .Rmd sale con el mismo nombre base que su HTML",
              rmds == [Path(h).stem + ".Rmd" for h in htmls if h.startswith("Soto")],
              rmds)
        check("el grupo sin .Rmd no inventa uno", len(rmds) == 1, rmds)
        check("no se cuela la basura de macOS",
              not any("._" in p.name or "MACOSX" in p.name for p in destino.iterdir()),
              [p.name for p in destino.iterdir()])
        check("los datos del alumno se reportan, no se descartan callados",
              any("myBD_rendimiento.csv" in o for o in omitidos), omitidos)
        check("lo agregado es lo que quedó en disco",
              len(agregados) == len(htmls) + len(rmds), (agregados, htmls, rmds))

        # Un zip que no se puede abrir no debe voltear la subida completa.
        roto = _Subido("Roto.zip", b"esto no es un zip")
        agregados2, omitidos2 = runner.extraer_entregas([roto], destino)
        check("un comprimido ilegible se reporta sin cortar la subida",
              agregados2 == [] and "Roto.zip" in omitidos2, (agregados2, omitidos2))

    # El .rar depende de una herramienta del sistema; se comprueba que la
    # decisión sea explícita y no un descarte en silencio.
    lector = runner._hay_lector_rar()
    if lector:
        check("hay con qué abrir .rar en este equipo", True)
    else:
        agregados3: list[str] = []
        omitidos3: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            runner._extraer_rar(b"Rar!\x1a\x07\x00", Path(tmp), agregados3,
                                omitidos3, "Grupo.rar")
        check("sin lector de .rar se avisa en vez de perder la entrega",
              any(".rar" in o for o in omitidos3), omitidos3)

    return resultado()


if __name__ == "__main__":
    raise SystemExit(main())
