"""
Lo que llega de U-Cursos y lo que queda en entregas/.

La descarga de U-Cursos es un zip con un comprimido por alumno adentro, y cada
uno trae el HTML renderizado, el .Rmd, los datos y basura de macOS. Estas
pruebas arman esa forma y comprueban que salgan solo las entregas, con nombres
que no se pisen entre grupos.

No hay red ni API acá: es todo desempaquetado.
"""

import shutil
import struct
import sys
import tempfile
import zipfile
import zlib
from io import BytesIO
from pathlib import Path

sys.path.insert(0, ".")

from pruebas.comun import check, resultado  # noqa: E402
from modulos.tareas import desempacar  # noqa: E402


def _bloque_rar(tipo: int, flags: int, resto: bytes) -> bytes:
    cuerpo = struct.pack("<BHH", tipo, flags, 7 + len(resto)) + resto
    return struct.pack("<H", zlib.crc32(cuerpo) & 0xFFFF) + cuerpo


def _rar(archivos: dict[str, bytes]) -> bytes:
    """Un .rar de verdad (RAR 4, sin comprimir): no hay con qué crearlos en el PC."""
    salida = b"Rar!\x1a\x07\x00" + _bloque_rar(0x73, 0, b"\x00" * 6)
    for nombre, datos in archivos.items():
        n = nombre.encode()
        resto = struct.pack("<IIBIIBBHI", len(datos), len(datos), 2, zlib.crc32(datos),
                            0x5A6D0000, 20, 0x30, len(n), 0x20) + n
        salida += _bloque_rar(0x74, 0x8000, resto) + datos
    return salida + _bloque_rar(0x7B, 0x4000, b"")


class _Subido:
    """Un archivo subido, con lo que lee extraer_entregas: .name y .getvalue()."""

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
        agregados, omitidos = desempacar.extraer_entregas([subido], destino)

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
        agregados2, omitidos2 = desempacar.extraer_entregas([roto], destino)
        check("un comprimido ilegible se reporta sin cortar la subida",
              agregados2 == [] and "Roto.zip" in omitidos2, (agregados2, omitidos2))

    # T2 de 2026-2: un grupo subió su repositorio con .git y el enunciado
    # renderizado al lado de su entrega, con un .Rmd de nombre distinto.
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("t2-repo/Tarea_2.html", b"<html>entrega</html>")
        zf.writestr("t2-repo/Tarea_2.Rmd", b"rmd de la entrega")
        zf.writestr("t2-repo/enunciado/Enunciado_T2.html", b"<html>enunciado</html>")
        zf.writestr("t2-repo/enunciado/Enunciado_T2.Rmd", b"rmd del enunciado")
        zf.writestr("t2-repo/.git/config", b"[core]")
        zf.writestr("t2-repo/.DS_Store", b"basura")
    subido = _Subido("Tarea 2.zip", _zip_de_ucursos({"Lagos_Pino__Eva_33333333.zip": buf.getvalue()}))
    with tempfile.TemporaryDirectory() as tmp:
        destino = Path(tmp) / "T2"
        agregados, omitidos = desempacar.extraer_entregas([subido], destino)
        check("el enunciado no se toma como una entrega más",
              sorted(agregados) == ["Lagos_Pino__Eva_33333333.Rmd", "Lagos_Pino__Eva_33333333.html"],
              agregados)
        check("el .Rmd es el de la entrega y no el del enunciado",
              (destino / "Lagos_Pino__Eva_33333333.Rmd").read_bytes() == b"rmd de la entrega")
        check("el enunciado se informa como omitido", any("es el enunciado" in o for o in omitidos), omitidos)
        check("la carpeta .git y .DS_Store no llenan la lista de omitidos",
              not any(".git" in o or ".DS_Store" in o for o in omitidos), omitidos)

    # Para recuperar a un alumno se sube el zip individual que da U-Cursos: la
    # entrega tiene que quedar con su nombre, igual que en el zip general.
    individual = _Subido("Lagos_Pino__Eva_33333333.zip",
                         _zip_de_grupo(b"<html>lagos</html>", b"rmd de lagos", "t1-Lagos"))
    with tempfile.TemporaryDirectory() as tmp:
        destino = Path(tmp) / "T1"
        agregados, omitidos = desempacar.extraer_entregas([individual], destino)
        check("el zip individual deja el HTML y el .Rmd con el nombre de U-Cursos",
              sorted(agregados) == ["Lagos_Pino__Eva_33333333.Rmd", "Lagos_Pino__Eva_33333333.html"],
              agregados)
        check("del zip individual sale la entrega y no otra cosa",
              (destino / "Lagos_Pino__Eva_33333333.html").read_bytes() == b"<html>lagos</html>")

    # Un zip subido con varios HTML sueltos conserva sus nombres.
    sueltos = _Subido("Varios.zip", _zip_de_ucursos({"Grupo1.html": b"<html>1</html>",
                                                     "Grupo2.html": b"<html>2</html>"}))
    with tempfile.TemporaryDirectory() as tmp:
        agregados, _ = desempacar.extraer_entregas([sueltos], Path(tmp) / "T1")
        check("varios HTML sueltos en el zip subido no toman el nombre del zip",
              sorted(agregados) == ["Grupo1.html", "Grupo2.html"], agregados)

    # El .rar depende de una herramienta del sistema; se comprueba que la
    # decisión sea explícita y no un descarte en silencio.
    lector = desempacar._hay_lector_rar()
    if lector:
        check("hay con qué abrir .rar en este equipo", True)
        # La página sube el .rar sin abrir, con el nombre que tendrá su HTML; el
        # chequeo lo abre en la carpeta de entregas (desempacar.desempacar_rars).
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp) / "T3"
            carpeta.mkdir()
            (carpeta / "T3-Soto, Pino.rar").write_bytes(_rar({
                "entrega/informe.html": b"<html>la entrega</html>",
                "entrega/informe.Rmd": b"el rmd",
                "entrega/Enunciado T3.html": b"<html>enunciado</html>",
                "__MACOSX/entrega/._informe.html": b"basura",
            }))
            agregados, omitidos = desempacar.desempacar_rars(carpeta)
            check("un .rar subido sin abrir deja su HTML y su .Rmd con el nombre del .rar",
                  sorted(agregados) == ["T3-Soto, Pino.Rmd", "T3-Soto, Pino.html"], agregados)
            check("del .rar sale la entrega y no el enunciado",
                  (carpeta / "T3-Soto, Pino.html").read_bytes() == b"<html>la entrega</html>")
            check("el enunciado del .rar se informa", any("enunciado" in o for o in omitidos), omitidos)
            otra_vez = desempacar.desempacar_rars(carpeta)
            check("un .rar ya abierto no se vuelve a abrir", otra_vez == ([], []), otra_vez)
            (carpeta / "T3-Vacio.rar").write_bytes(_rar({"datos.csv": b"a,b"}))
            _, omitidos = desempacar.desempacar_rars(carpeta)
            check("un .rar sin HTML se avisa", any("T3-Vacio.rar" in o for o in omitidos), omitidos)
            (carpeta / "T3-Roto.rar").write_bytes(b"Rar!\x1a\x07\x00 roto")
            _, omitidos = desempacar.desempacar_rars(carpeta)
            check("un .rar que no se puede abrir se avisa",
                  any("T3-Roto.rar" in o for o in omitidos), omitidos)
    else:
        agregados3: list[str] = []
        omitidos3: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            desempacar._extraer_rar(b"Rar!\x1a\x07\x00", Path(tmp), agregados3,
                                omitidos3, "Grupo.rar")
        check("sin lector de .rar se avisa en vez de perder la entrega",
              any(".rar" in o for o in omitidos3), omitidos3)

    return resultado()


if __name__ == "__main__":
    raise SystemExit(main())
