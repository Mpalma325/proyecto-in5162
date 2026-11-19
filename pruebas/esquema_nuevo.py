"""
El esquema común de notas.csv y del log: lo que necesitan la revisión docente y
la escala de notas, sin que cambie nada de lo que ya funciona.

Corre sobre la plantilla, con tablas armadas acá y nombres inventados: no lee
datos de alumnos reales.
"""

import csv
import sys
from unittest.mock import patch

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import check, resultado, semestre_desechable, titulo  # noqa: E402


def _escribir_csv(ruta, campos, filas):
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)


def _leer_csv(ruta):
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        return lector.fieldnames, list(lector)


def escritura_que_conserva(tmp, sid):
    from modulos.datos import _csv, alumnos
    from modulos.datos.esquema import COLUMNAS_NOTAS, NOTAS

    titulo("1. escribir conserva las columnas que no conoce")
    ruta = tmp / NOTAS
    viejas = ["Correo", "Flujo", "Item", "Enviado", "Respondio", "Nota", "Originalidad"]
    _escribir_csv(ruta, viejas[:3] + ["Comentario"] + viejas[3:], [
        {"Correo": "ana.prueba@correo.test", "Flujo": "test", "Item": "1", "Comentario": "revisar",
         "Enviado": "2026-11-02T09:00:00-03:00", "Respondio": "", "Nota": "", "Originalidad": ""},
    ])
    _, filas = _leer_csv(ruta)
    _csv.escribir(NOTAS, filas, COLUMNAS_NOTAS, sid)
    campos, filas = _leer_csv(ruta)
    check("la columna desconocida sigue ahí, con su valor",
          "Comentario" in campos and filas[0]["Comentario"] == "revisar", (campos, filas))
    check("primero las del llamador, después las que solo tenía el archivo",
          campos == list(COLUMNAS_NOTAS) + ["Comentario"], campos)
    check("no queda el archivo temporal", not (tmp / (NOTAS + ".tmp")).exists())

    titulo("2. si la escritura falla a mitad, queda el archivo anterior entero")
    antes = ruta.read_bytes()
    real = csv.DictWriter

    class DictWriterQueFalla(real):
        def writerow(self, fila):
            self.n = getattr(self, "n", 0) + 1
            if self.n == 3:  # la cabecera no pasa por acá: es la fila 3 de datos
                raise OSError("disco lleno")
            return super().writerow(fila)

    filas_nuevas = [dict(filas[0], Item=str(i)) for i in range(1, 6)]
    with patch.object(_csv.csv, "DictWriter", DictWriterQueFalla):
        try:
            _csv.escribir(NOTAS, filas_nuevas, COLUMNAS_NOTAS, sid)
            check("la falla llega al llamador", False, "no levantó")
        except OSError:
            check("la falla llega al llamador", True)
    check("el archivo anterior quedó igual, byte a byte", ruta.read_bytes() == antes)
    check("y sin el temporal a medio escribir", not (tmp / (NOTAS + ".tmp")).exists())

    titulo("3. alumnos.csv conserva las columnas del profesor al asignar grupos")
    _escribir_csv(tmp / "alumnos.csv", ["Nombre", "Correo", "CorreosAlternativos", "Grupo"], [
        {"Nombre": "Ana Prueba", "Correo": "ana.prueba@correo.test",
         "CorreosAlternativos": "ana.otra@correo.test", "Grupo": ""},
        {"Nombre": "Beto Ensayo", "Correo": "beto.ensayo@correo.test",
         "CorreosAlternativos": "", "Grupo": ""},
    ])
    alumnos.asignar_grupos_faltantes(7, sid)
    campos, filas = _leer_csv(tmp / "alumnos.csv")
    check("los grupos quedaron asignados", all(f["Grupo"] for f in filas), filas)
    check("CorreosAlternativos sigue con su valor",
          "CorreosAlternativos" in campos and filas[0]["CorreosAlternativos"] == "ana.otra@correo.test",
          (campos, filas))


with semestre_desechable(base="_template", sid="_tmp_esquema") as (sid, tmp):
    escritura_que_conserva(tmp, sid)

sys.exit(resultado())
