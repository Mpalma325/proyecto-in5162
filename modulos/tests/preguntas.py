import csv
from dataclasses import dataclass, field

from . import config


@dataclass
class GrupoPreguntas:
    preguntas: list[str]   # solo las no vacías
    pautas: list[str]      # alineadas con las preguntas

    @property
    def n_preguntas(self) -> int:
        return len(self.preguntas)


@dataclass
class SemanaInfo:
    semana: int
    tema: str
    fecha_entrega: str
    control: GrupoPreguntas
    tratamiento: GrupoPreguntas

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


def cargar_semana(semana: int) -> SemanaInfo:
    if not config.PREGUNTAS_CSV.exists():
        raise FileNotFoundError(
            f"No existe {config.PREGUNTAS_CSV}. "
            f"Pon el CSV de preguntas y respuestas ahí."
        )

    with config.PREGUNTAS_CSV.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for fila in reader:
            try:
                num = int(fila.get("Semana", "").strip())
            except ValueError:
                continue
            if num == semana:
                return _parsear_fila(fila, semana)

    raise ValueError(
        f"No encontré la semana {semana} en {config.PREGUNTAS_CSV}. "
        f"Verifica que la columna 'Semana' tenga el número exacto."
    )


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


def _parsear_fila(fila: dict, semana: int) -> SemanaInfo:
    fila_limpia = {(k or "").strip(): (v or "").strip() for k, v in fila.items()}

    tema = fila_limpia.get("Tema", "").strip()
    fecha = fila_limpia.get("Fecha de Entrega", "").strip()

    control = _extraer_grupo(fila_limpia, "Control")
    tratamiento = _extraer_grupo(fila_limpia, "Tratamiento")

    if control.n_preguntas == 0 and tratamiento.n_preguntas == 0:
        raise ValueError(f"La semana {semana} no tiene ninguna pregunta definida.")

    if tratamiento.n_preguntas == 0:
        tratamiento = GrupoPreguntas(
            preguntas=list(control.preguntas),
            pautas=list(control.pautas),
        )

    return SemanaInfo(
        semana=semana,
        tema=tema,
        fecha_entrega=fecha,
        control=control,
        tratamiento=tratamiento,
    )
