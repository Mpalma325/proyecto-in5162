"""
La escala de notas de los tests: cómo se pasa del logro a la nota y de vuelta.

El logro es el puntaje obtenido sobre el máximo, entre 0 y 1. La nota la calcula
el código con la escala del semestre, no el modelo. Vive en `escala_notas.json`,
en la raíz del semestre:

    {"tipo": "lineal", "minima": 4.0, "maxima": 7.0, "decimales": 1,
     "aprobacion": null, "exigencia": null, "puntaje_maximo_pregunta": 3}

- Lineal: nota = minima + logro × (maxima − minima).
- Dos tramos (la escala con exigencia): bajo la exigencia el logro se reparte
  entre la mínima y la nota de aprobación; sobre ella, entre la aprobación y la
  máxima. Con 1,0 / 4,0 / 7,0 y exigencia 0,6 es la escala del 60 %.

Sin el archivo rige 4,0–7,0 con un decimal: con la rúbrica de 0 a 3 por
pregunta da lo mismo que pedía el prompt de siempre (4 + promedio de los
puntajes), así que las notas de los semestres que ya existen no cambian.

Solo aplica a Tests. Tareas tiene la suya (modulos/tareas/escala.py).

Las cuentas se hacen con fracciones exactas y el redondeo es hacia arriba en el
medio (6,25 → 6,3). El `round()` de Python redondea al par y daría 6,2.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from decimal import Decimal
from fractions import Fraction

ARCHIVO = "escala_notas.json"

LINEAL = "lineal"
DOS_TRAMOS = "dos_tramos"


def _fraccion(x) -> Fraction:
    """Un número leído de donde venga (float, texto con coma, Decimal), sin el ruido del float."""
    if isinstance(x, Fraction):
        return x
    if isinstance(x, (int, Decimal)):
        return Fraction(x)
    if isinstance(x, float):
        return Fraction(repr(x))
    texto = str(x).strip().replace(",", ".")
    if not texto:
        raise ValueError("número vacío")
    return Fraction(texto)


def _num(x) -> str:
    """4.0 → "4"; 4.5 → "4,5". Para describir la escala en una línea."""
    f = _fraccion(x)
    if f.denominator == 1:
        return str(f.numerator)
    return f"{float(f):g}".replace(".", ",")


@dataclass(frozen=True)
class Escala:
    tipo: str = LINEAL
    minima: float = 4.0
    maxima: float = 7.0
    decimales: int = 1
    aprobacion: float | None = None
    exigencia: float | None = None
    puntaje_maximo_pregunta: float = 3

    def validar(self) -> Escala:
        """La misma escala, o ValueError diciendo qué está mal."""
        if self.tipo not in (LINEAL, DOS_TRAMOS):
            raise ValueError(f"Tipo de escala desconocido: {self.tipo!r} (lineal o dos_tramos)")
        if not 0 <= self.minima < self.maxima <= 1000:
            raise ValueError(f"La escala va de {self.minima} a {self.maxima}: "
                             "la mínima tiene que ser menor que la máxima, entre 0 y 1000.")
        if self.decimales not in (0, 1, 2):
            raise ValueError(f"Decimales: {self.decimales!r} (0, 1 o 2)")
        if not self.puntaje_maximo_pregunta > 0:
            raise ValueError("El puntaje máximo por pregunta tiene que ser mayor que cero.")
        if self.tipo == DOS_TRAMOS:
            if self.aprobacion is None or self.exigencia is None:
                raise ValueError("Una escala de dos tramos necesita la nota de aprobación y la exigencia.")
            if not self.minima < self.aprobacion < self.maxima:
                raise ValueError(f"La aprobación ({self.aprobacion}) tiene que quedar entre "
                                 f"la mínima y la máxima.")
            if not 0 < self.exigencia < 1:
                raise ValueError(f"La exigencia ({self.exigencia}) va entre 0 y 1 (0,6 es 60 %).")
        return self

    # ------------------------------------------------------------ cuentas

    def logro_de(self, puntajes) -> Fraction:
        """El logro de una corrección: suma de puntajes sobre el máximo posible."""
        puntajes = [_fraccion(p) for p in puntajes]
        if not puntajes:
            raise ValueError("Sin puntajes no hay logro.")
        maximo = _fraccion(self.puntaje_maximo_pregunta)
        for p in puntajes:
            if not 0 <= p <= maximo:
                raise ValueError(f"Puntaje fuera de rango: {float(p):g} (de 0 a {_num(maximo)})")
        return sum(puntajes) / (maximo * len(puntajes))

    def nota_exacta(self, logro) -> Fraction:
        """La nota sin redondear."""
        logro = _fraccion(logro)
        if not 0 <= logro <= 1:
            raise ValueError(f"El logro va de 0 a 1: {float(logro):g}")
        minima, maxima = _fraccion(self.minima), _fraccion(self.maxima)
        if self.tipo == LINEAL:
            return minima + logro * (maxima - minima)
        aprobacion, exigencia = _fraccion(self.aprobacion), _fraccion(self.exigencia)
        if logro < exigencia:
            return minima + (aprobacion - minima) * logro / exigencia
        return aprobacion + (maxima - aprobacion) * (logro - exigencia) / (1 - exigencia)

    def redondear(self, nota) -> Decimal:
        """Con `decimales`, y hacia arriba en el medio: 6,25 → 6,3."""
        escala = 10 ** self.decimales
        entero = math.floor(_fraccion(nota) * escala + Fraction(1, 2))
        return Decimal(entero).scaleb(-self.decimales)

    def nota(self, logro) -> Decimal:
        """La nota que corresponde a ese logro, ya redondeada."""
        return self.redondear(self.nota_exacta(logro))

    def logro(self, nota) -> Fraction | None:
        """La inversa: el logro de una nota. None si la nota queda fuera de la escala.

        Una nota fuera de rango (un 3,0 puesto a mano en una escala de 4 a 7) no
        tiene logro: queda fija aunque la escala cambie.
        """
        nota = _fraccion(nota)
        minima, maxima = _fraccion(self.minima), _fraccion(self.maxima)
        if not minima <= nota <= maxima:
            return None
        if self.tipo == LINEAL:
            return (nota - minima) / (maxima - minima)
        aprobacion, exigencia = _fraccion(self.aprobacion), _fraccion(self.exigencia)
        if nota < aprobacion:
            return exigencia * (nota - minima) / (aprobacion - minima)
        return exigencia + (1 - exigencia) * (nota - aprobacion) / (maxima - aprobacion)

    # ------------------------------------------------------------ texto

    def texto(self, nota) -> str:
        """Como se escribe en notas.csv y en el correo: "6,5", "83", "6,50"."""
        return str(self.redondear(nota)).replace(".", ",")

    def rango(self) -> str:
        """Para una persona: "4,0 a 7,0". Es lo que va en {ESCALA} del correo de la pregunta."""
        return f"{self.texto(self.minima)} a {self.texto(self.maxima)}"

    def describir(self) -> str:
        """Una línea para el log: "4-7/1" o "1-7/1 4 al 60 %"."""
        base = f"{_num(self.minima)}-{_num(self.maxima)}/{self.decimales}"
        if self.tipo == DOS_TRAMOS:
            base += f" {_num(self.aprobacion)} al {_num(_fraccion(self.exigencia) * 100)} %"
        return base

    def como_dict(self) -> dict:
        return asdict(self)


POR_DEFECTO = Escala()


def texto_logro(logro) -> str:
    """El logro como se guarda: de 0 a 1, con cuatro decimales y punto."""
    return f"{float(_fraccion(logro)):.4f}"


def desde_dict(datos: dict) -> Escala:
    """Una escala desde lo leído del JSON. Las claves que falten toman el valor por defecto."""
    if not isinstance(datos, dict):
        raise ValueError("La escala tiene que ser un objeto JSON.")
    conocidas = set(POR_DEFECTO.como_dict())
    extra = set(datos) - conocidas
    if extra:
        raise ValueError(f"Claves desconocidas en la escala: {sorted(extra)}")
    return Escala(**{**POR_DEFECTO.como_dict(), **datos}).validar()


def leer(semestre_id: str | None = None) -> Escala:
    """La escala del semestre, o la de siempre (4,0–7,0) si no tiene `escala_notas.json`."""
    from modulos import semestre as _semestre

    ruta = _semestre.raiz(semestre_id) / ARCHIVO
    if not ruta.exists():
        return POR_DEFECTO
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{ARCHIVO} no es JSON válido: {e}") from e
    return desde_dict(datos)
