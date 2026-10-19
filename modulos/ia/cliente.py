"""
Cliente de OpenAI compartido.

Antes vivía duplicado: tests llamaba a la API para evaluar respuestas y generar
resúmenes, tareas para generar preguntas en JSON. La llamada era la misma en
los tres casos; lo único distinto eran los prompts, que se quedan en cada flujo.
"""

import atexit
import json
import os
import re
from dataclasses import dataclass, field

from openai import OpenAI

_api_key_provider = None
_ajustes = {"modelo": "gpt-5.4-mini", "temperatura": 0.2, "max_tokens": 3000,
            "servidor": None, "timeout": None, "razonamiento": None}

# Los modelos con razonamiento (Qwen 3.x, Gemma 4 y otros que se corren en
# local) pueden devolver lo que pensaron entre <think>...</think> antes de la
# respuesta. Eso no es parte del correo ni del HTML que se parsea, así que se
# saca acá, en el único lugar por donde pasan todas las respuestas.
_PENSAMIENTO = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


# Lo que se gastó en este proceso, por modelo: [llamadas, tokens de entrada,
# tokens de salida]. Al terminar se imprime una línea por modelo, y el sitio la
# lee de la salida de cada trabajo para mostrar cuánto costó
# (web/public/consumo.js). Si cambia la forma de la línea, cambia ese lector.
_consumo: dict[str, list[int]] = {}


def registrar_uso(modelo: str | None, entrada: int | None, salida: int | None) -> None:
    """Suma una llamada al consumo del proceso. completar() la llama sola; las
    llamadas que no pasan por acá (tareas/corregir.py) la llaman a mano."""
    c = _consumo.setdefault(modelo or "desconocido", [0, 0, 0])
    c[0] += 1
    c[1] += int(entrada or 0)
    c[2] += int(salida or 0)


def consumo() -> dict[str, tuple[int, int, int]]:
    """(llamadas, tokens de entrada, tokens de salida) por modelo, en este proceso."""
    return {m: tuple(v) for m, v in _consumo.items()}


def linea_consumo(modelo: str, llamadas: int, entrada: int, salida: int, precios: dict | None = None) -> str:
    """La línea que queda en la salida del trabajo. Con precios (US$ por millón
    de tokens, [entrada, salida]) agrega el costo de ese momento."""
    texto = (f"Consumo de API ({modelo}): {llamadas} llamada{'' if llamadas == 1 else 's'}, "
             f"{entrada} tokens de entrada, {salida} de salida")
    p = (precios or {}).get(modelo)
    if isinstance(p, list) and len(p) == 2:
        costo = (entrada * float(p[0]) + salida * float(p[1])) / 1_000_000
        texto += f", US$ {costo:.4f}".replace(".", ",")
    return texto + "."


def _informar_consumo() -> None:
    if not _consumo:
        return
    # Los precios llegan del sitio como variable de entorno (Configuración ›
    # Parámetros); sin ellos la línea dice solo los tokens.
    try:
        precios = json.loads(os.environ.get("PRECIOS_API") or "{}")
    except ValueError:
        precios = {}
    for modelo, (llamadas, entrada, salida) in sorted(_consumo.items()):
        print(linea_consumo(modelo, llamadas, entrada, salida, precios), flush=True)


atexit.register(_informar_consumo)


def configurar(api_key_provider, modelo: str | None = None,
               temperatura: float | None = None, max_tokens: int | None = None,
               servidor: str | None = None, timeout: float | None = None,
               razonamiento: str | None = None) -> None:
    """Registra cómo obtener la API key y los valores por defecto del modelo.

    `servidor` es la URL de una API compatible con la de OpenAI. Vacío usa
    OpenAI. Para un modelo local con Ollama es "http://127.0.0.1:11434/v1", y
    la key puede ser cualquier texto: Ollama no la revisa.

    `razonamiento` se manda como `reasoning_effort` ("none", "low", "medium",
    "high"). Vacío no manda nada y cada modelo usa lo suyo. En los modelos
    locales con razonamiento conviene "none": con él activo, qwen3.5:4b gastó
    todo el tope de tokens pensando y devolvió la respuesta vacía.
    """
    global _api_key_provider
    _api_key_provider = api_key_provider
    if modelo is not None:
        _ajustes["modelo"] = modelo
    if temperatura is not None:
        _ajustes["temperatura"] = temperatura
    if max_tokens is not None:
        _ajustes["max_tokens"] = max_tokens
    if servidor is not None:
        _ajustes["servidor"] = servidor or None
    if timeout is not None:
        _ajustes["timeout"] = timeout
    if razonamiento is not None:
        _ajustes["razonamiento"] = razonamiento or None


def ajustes() -> dict:
    """Copia de la configuración vigente, para dejarla registrada."""
    return dict(_ajustes)


def _cliente() -> OpenAI:
    if _api_key_provider is None:
        raise RuntimeError(
            "El módulo ia no tiene API key. Llama a ia.configurar(...) pasándole "
            "una función que devuelva la key."
        )
    extra = {}
    if _ajustes["servidor"]:
        extra["base_url"] = _ajustes["servidor"]
    if _ajustes["timeout"]:
        extra["timeout"] = _ajustes["timeout"]
    return OpenAI(api_key=_api_key_provider(), **extra)


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
    if _ajustes["razonamiento"]:
        extra["reasoning_effort"] = _ajustes["razonamiento"]

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
    registrar_uso(_ajustes["modelo"], getattr(uso, "prompt_tokens", 0), getattr(uso, "completion_tokens", 0))
    return Respuesta(
        texto=_PENSAMIENTO.sub("", resp.choices[0].message.content or "").strip(),
        meta={
            "modelo": _ajustes["modelo"],
            "prompt_tokens": getattr(uso, "prompt_tokens", None),
            "completion_tokens": getattr(uso, "completion_tokens", None),
            "total_tokens": getattr(uso, "total_tokens", None),
        },
    )
