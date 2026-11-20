"""
Las preguntas de cada instancia de test, leídas de `tests_semanales/data/preguntas.csv`.

El archivo viene en dos formatos, y se distinguen por la columna del id:

- `Semana` (2026-2 y antes): cada fila es una semana ya confirmada. Se llama
  «Semana N», el correo lleva el asunto «… Módulo N: tema» y el texto «La
  pregunta de la semana es». Las columnas nuevas no se usan.
- `Instancia` (semestres nuevos, lo escribe la página): un id entero que el
  docente no ve, más `Tipo` y `Numero` («Control 2»), `Estado` (borrador o
  confirmada), `Envio` y `Cierre` (fecha y hora ISO con zona). El asunto es
  «Control 2: tema».

Con las dos columnas a la vez el archivo es un error: no se sabe cuál manda.
El id es el `Item` de notas.csv, del log y del panel en los dos formatos.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from modulos.datos import lector_csv

from . import config

ID_VALIDO = re.compile(r"[1-9][0-9]{0,2}")
COLUMNAS_INSTANCIA = ("Instancia", "Tipo", "Numero", "Estado", "Envio", "Cierre")
TIPO_LEGADO = "Semana"
TIPO_POR_DEFECTO = "Instancia"
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


class PreguntasError(ValueError):
    """preguntas.csv no se puede usar como está. Es ValueError: quien ya atrapaba eso, sigue."""


@dataclass
class GrupoPreguntas:
    preguntas: list[str]   # solo las no vacías
    pautas: list[str]      # alineadas con las preguntas

    @property
    def n_preguntas(self) -> int:
        return len(self.preguntas)


@dataclass
class SemanaInfo:
    """Una instancia de test. `semana` es el id (columna Instancia o Semana)."""
    semana: int
    tema: str
    fecha_entrega: str
    control: GrupoPreguntas
    tratamiento: GrupoPreguntas
    tipo: str = TIPO_LEGADO
    numero: int | None = None
    estado: str = "confirmada"
    envio: str = ""
    cierre: str = ""
    legado: bool = True

    def __post_init__(self):
        if self.numero is None:
            self.numero = self.semana

    @property
    def instancia(self) -> int:
        return self.semana

    @property
    def nombre(self) -> str:
        """Lo que ve el docente y el alumno: «Control 2», o «Semana 4» en el formato antiguo."""
        return f"{self.tipo} {self.numero}"

    @property
    def borrador(self) -> bool:
        return self.estado == "borrador"

    @property
    def preguntas(self) -> list[str]:
        return self.control.preguntas

    @property
    def pautas(self) -> list[str]:
        return self.control.pautas

    @property
    def n_preguntas(self) -> int:
        return self.control.n_preguntas

    def para_grupo(self, grupo: str) -> GrupoPreguntas:
        if grupo.lower().strip() == "tratamiento":
            return self.tratamiento
        return self.control


@dataclass
class ArchivoPreguntas:
    columna: str                 # "Instancia" o "Semana"
    filas: dict[int, dict]       # id -> fila limpia, en el orden del archivo
    problemas: list[str]         # filas que no se pudieron leer; se avisan, no paran nada
    repetidos: set[int]

    @property
    def legado(self) -> bool:
        return self.columna == "Semana"


def _limpia(fila: dict) -> dict:
    return {(k or "").strip(): (v or "").strip() for k, v in fila.items() if k is not None}


def leer_archivo(ruta: Path | None = None) -> ArchivoPreguntas:
    """Las filas de preguntas.csv por id, con lo que no se pudo leer aparte.

    Sin archivo, o con solo la cabecera, no hay instancias (no es un error).
    Un id inválido («4a», «0», «1000») o repetido se informa en `problemas` y
    la fila no se usa. Un archivo con `Semana` e `Instancia` a la vez levanta
    PreguntasError.
    """
    ruta = ruta or config.PREGUNTAS_CSV
    if not Path(ruta).exists():
        return ArchivoPreguntas("Instancia", {}, [], set())
    # Coma o punto y coma, UTF-8 o cp1252: puede venir de una planilla.
    lector = lector_csv(ruta)
    columnas = [(c or "").strip() for c in (lector.fieldnames or [])]
    filas = [_limpia(x) for x in lector]
    if "Semana" in columnas and "Instancia" in columnas:
        raise PreguntasError("preguntas.csv tiene las columnas Semana e Instancia a la vez: "
                             "deja solo una (Instancia en los semestres nuevos).")
    if not columnas:
        return ArchivoPreguntas("Instancia", {}, [], set())
    if "Semana" not in columnas and "Instancia" not in columnas:
        raise PreguntasError("preguntas.csv no tiene la columna del id (Instancia, o Semana en el formato antiguo).")
    columna = "Instancia" if "Instancia" in columnas else "Semana"

    por_id: dict[int, dict] = {}
    problemas, repetidos = [], set()
    for n, fila in enumerate(filas, start=2):
        crudo = fila.get(columna, "")
        if not crudo:
            if any(fila.values()):
                problemas.append(f"la fila {n} no tiene {columna}: no se usa")
            continue  # una fila en blanco al final es normal
        if not ID_VALIDO.fullmatch(crudo):
            problemas.append(f"la fila {n} tiene {columna} «{crudo}», que no es un número de 1 a 999: no se usa")
            continue
        i = int(crudo)
        if i in por_id:
            repetidos.add(i)
            problemas.append(f"{columna} {i} está repetida (fila {n})")
            continue
        por_id[i] = fila
    return ArchivoPreguntas(columna, por_id, problemas, repetidos)


def texto_fecha(iso: str) -> str:
    """'2026-10-19T10:15:00-03:00' -> 'lunes 19/10/2026, 10:15', en la hora que trae escrita.

    Es lo que el correo muestra como fecha de entrega cuando la fila no la trae
    escrita, y lo mismo que escribe la página (preguntas.js, textoFecha).
    """
    try:
        d = datetime.fromisoformat(str(iso).strip().replace("Z", "+00:00"))
    except ValueError:
        return ""
    return f"{_DIAS[d.weekday()]} {d:%d/%m/%Y}, {d.hour}:{d:%M}"


def _numero(texto: str, defecto: int) -> int:
    return int(texto) if ID_VALIDO.fullmatch(texto or "") else defecto


def _estado(texto: str) -> str:
    # Vacío es confirmada, como dice el diseño (1.1). Un valor que no se
    # entiende se trata como borrador: así no sale nada que nadie confirmó.
    t = (texto or "").strip().lower()
    return "confirmada" if t in ("", "confirmada") else "borrador"


def instancias(ruta: Path | None = None, avisar: bool = False) -> dict[int, "SemanaInfo"]:
    """Todas las instancias que se pueden leer, por id. Las filas sin preguntas no entran."""
    archivo = leer_archivo(ruta)
    if avisar:
        for p in archivo.problemas:
            print(f"  ⚠ preguntas.csv: {p}")
    salida = {}
    for i, fila in archivo.filas.items():
        try:
            salida[i] = _parsear_fila(fila, i, legado=archivo.legado)
        except ValueError:
            pass
    return salida


def cargar_semana(semana: int) -> SemanaInfo:
    """La instancia con ese id. Levanta PreguntasError (un ValueError) si no se puede usar."""
    archivo = leer_archivo()
    for p in archivo.problemas:
        print(f"  ⚠ preguntas.csv: {p}")
    if semana in archivo.repetidos:
        raise PreguntasError(f"El id {semana} está repetido en preguntas.csv: no sé cuál fila usar.")
    if semana not in archivo.filas:
        if not archivo.filas:
            raise PreguntasError("Todavía no hay tests en preguntas.csv: créalos en Configuración › Preguntas.")
        if archivo.legado:
            raise PreguntasError(
                f"No encontré la semana {semana} en {config.PREGUNTAS_CSV}. "
                f"Verifica que la columna 'Semana' tenga el número exacto."
            )
        raise PreguntasError(f"La instancia {semana} no existe en preguntas.csv; créala en Configuración › Preguntas.")
    return _parsear_fila(archivo.filas[semana], semana, legado=archivo.legado)


def asunto(info: SemanaInfo) -> str:
    """El asunto del correo de la pregunta. Es también con lo que se reconocen las respuestas."""
    if info.legado:
        return f"Evaluación de Progreso Individual Módulo {info.semana}: {info.tema}"
    return f"{info.nombre}: {info.tema}" if info.tema else info.nombre


def _extraer_grupo(fila: dict, prefijo: str) -> GrupoPreguntas:
    preguntas = []
    pautas = []
    for i in (1, 2, 3):
        p = (fila.get(f"{prefijo} P{i}") or "").strip()
        pa = (fila.get(f"{prefijo} Pauta P{i}") or "").strip()
        if p:
            preguntas.append(p)
            pautas.append(pa)
    return GrupoPreguntas(preguntas=preguntas, pautas=pautas)


def _parsear_fila(fila: dict, semana: int, legado: bool | None = None) -> SemanaInfo:
    fila_limpia = {(k or "").strip(): (v or "").strip() for k, v in fila.items()}
    if legado is None:
        legado = "Instancia" not in fila_limpia

    tema = fila_limpia.get("Tema", "").strip()
    fecha = fila_limpia.get("Fecha de Entrega", "").strip()

    control = _extraer_grupo(fila_limpia, "Control")
    tratamiento = _extraer_grupo(fila_limpia, "Tratamiento")

    if control.n_preguntas == 0 and tratamiento.n_preguntas == 0:
        if legado:
            raise ValueError(f"La semana {semana} no tiene ninguna pregunta definida.")
        tipo = fila_limpia.get("Tipo") or TIPO_POR_DEFECTO
        raise ValueError(f"{tipo} {_numero(fila_limpia.get('Numero', ''), semana)} no tiene ninguna pregunta definida.")

    if tratamiento.n_preguntas == 0:
        tratamiento = GrupoPreguntas(
            preguntas=list(control.preguntas),
            pautas=list(control.pautas),
        )

    if legado:
        return SemanaInfo(semana=semana, tema=tema, fecha_entrega=fecha,
                          control=control, tratamiento=tratamiento)

    cierre = fila_limpia.get("Cierre", "")
    return SemanaInfo(
        semana=semana,
        tema=tema,
        # Manda el cierre (es también la hora de la evaluación); la columna Fecha
        # de Entrega, que la página escribe a partir de él, queda de respaldo.
        fecha_entrega=texto_fecha(cierre) or fecha,
        control=control,
        tratamiento=tratamiento,
        tipo=fila_limpia.get("Tipo") or TIPO_POR_DEFECTO,
        numero=_numero(fila_limpia.get("Numero", ""), semana),
        estado=_estado(fila_limpia.get("Estado", "")),
        envio=fila_limpia.get("Envio", ""),
        cierre=cierre,
        legado=False,
    )
