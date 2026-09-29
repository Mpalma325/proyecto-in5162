"""Valida las notas según la escala configurada en los prompts del semestre."""

import json
from decimal import Decimal, InvalidOperation

from . import config


def validar_nota(valor) -> float:
    try:
        nota = Decimal(str(valor))
    except InvalidOperation as exc:
        raise ValueError(f'Nota inválida: {valor!r}') from exc
    if not nota.is_finite():
        raise ValueError(f'Nota inválida: {valor!r}')
    archivo = config.PROMPTS / 'escala.json'
    if archivo.exists():
        valores = json.loads(archivo.read_text(encoding='utf-8'))['valores']
        if nota not in {Decimal(str(v)) for v in valores}:
            raise ValueError(f'Nota {valor} fuera de la escala permitida: {valores}')
    elif not Decimal(str(config.NOTA_MIN)) <= nota <= Decimal(str(config.NOTA_MAX)):
        raise ValueError(f'Nota {valor} fuera de {config.NOTA_MIN} a {config.NOTA_MAX}')
    return float(nota)
