"""
Cliente de OpenAI compartido.

Antes vivía duplicado: tests llamaba a la API para evaluar respuestas y generar
resúmenes, tareas para generar preguntas en JSON. La llamada era la misma en
los tres casos; lo único distinto eran los prompts, que se quedan en cada flujo.
"""

import json
from dataclasses import dataclass, field

from openai import OpenAI

_api_key_provider = None
_ajustes = {"modelo": "gpt-5.4-mini", "temperatura": 0.2, "max_tokens": 3000}


def configurar(api_key_provider, modelo: str | None = None,
               temperatura: float | None = None, max_tokens: int | None = None) -> None:
    """Registra cómo obtener la API key y los valores por defecto del modelo."""
    global _api_key_provider
    _api_key_provider = api_key_provider
    if modelo is not None:
        _ajustes["modelo"] = modelo
    if temperatura is not None:
        _ajustes["temperatura"] = temperatura
    if max_tokens is not None:
        _ajustes["max_tokens"] = max_tokens


def _cliente() -> OpenAI:
    if _api_key_provider is None:
        raise RuntimeError(
            "El módulo ia no tiene API key. Llama a ia.configurar(...) pasándole "
            "una función que devuelva la key."
        )
    return OpenAI(api_key=_api_key_provider())


class Texto(str):
    """El texto que devolvió el modelo, que además recuerda qué costó producirlo.

    Es un `str` de verdad, así que quien solo quiera el texto lo usa sin
    enterarse. Existe para que un flujo pueda registrar el modelo y los tokens
    sin obligar a cambiar la firma de las funciones que lo devuelven, ni los
    llamadores que ya tratan el resultado como una cadena.

    Quien reciba esto desde fuera debe leerlo como `getattr(x, "meta", {})`:
    puede venir un `str` pelado (por ejemplo desde una prueba con mocks).
    """

    meta: dict

    def __new__(cls, texto: str, meta: dict | None = None):
        obj = super().__new__(cls, texto)
        obj.meta = meta or {}
        return obj


@dataclass
class Respuesta:
    """Lo que devolvió el modelo, más el detalle de consumo."""
    texto: str
    meta: dict = field(default_factory=dict)

    def con_meta(self) -> Texto:
        """El texto, cargando su propia metadata."""
        return Texto(self.texto, self.meta)

    @property
    def datos(self) -> dict:
        """El texto parseado como JSON (solo si se pidió formato JSON)."""
        try:
            return json.loads(self.texto)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"El modelo devolvió algo que no es JSON válido:\n{self.texto[:500]}..."
            ) from e


def completar(system: str, user: str, *, temperatura: float | None = None,
              max_tokens: int | None = None, json_mode: bool = False) -> Respuesta:
    """Una llamada al modelo. Devuelve el texto y el consumo de tokens."""
    extra = {"response_format": {"type": "json_object"}} if json_mode else {}

    resp = _cliente().chat.completions.create(
        model=_ajustes["modelo"],
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=_ajustes["temperatura"] if temperatura is None else temperatura,
        max_completion_tokens=_ajustes["max_tokens"] if max_tokens is None else max_tokens,
        **extra,
    )

    uso = resp.usage
    return Respuesta(
        texto=resp.choices[0].message.content or "",
        meta={
            "modelo": _ajustes["modelo"],
            "prompt_tokens": getattr(uso, "prompt_tokens", None),
            "completion_tokens": getattr(uso, "completion_tokens", None),
            "total_tokens": getattr(uso, "total_tokens", None),
        },
    )
