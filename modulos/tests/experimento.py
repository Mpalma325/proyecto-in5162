"""
Prueba un prompt de evaluación distinto sobre respuestas ya corregidas.

Toma N respuestas al azar de las que el curso ya evaluó, las vuelve a pasar por
el modelo con un prompt candidato, y compara casilla por casilla contra la nota
y la originalidad que se les puso en su momento. Sirve para saber si un cambio
de prompt corre la distribución de originalidad antes de aplicarlo al curso.

    python -m modulos.tests.experimento --prompt nuevo.md
    python -m modulos.tests.experimento --prompt nuevo.md -n 30 --semana 4
    python -m modulos.tests.experimento --prompt nuevo.md -n 10 --dry-run

Para comparar modelos en vez de prompts, se deja el prompt vigente y se cambia el
modelo. Con `--local` va contra Ollama en este PC:

    python -m modulos.tests.experimento --local --modelo qwen3.5:4b --todas

Con `--todas` se reevalúan todas las respuestas del semestre, y el CSV de salida
se escribe fila por fila: si la corrida se corta, volver a lanzarla con la misma
`--salida` retoma donde quedó, sin repetir lo ya hecho.

Con `--historico` recorre todos los semestres, uno detrás de otro, y deja cada
resultado en `semestres/<id>/experimentos/<modelo>.csv`. Es la corrida pensada
para dejar el PC trabajando de noche: mientras dura, Windows no suspende el
equipo, y si se corta basta con lanzar el mismo comando otra vez.

    python -m modulos.tests.experimento --local --modelo qwen3.5:4b --historico

Con `--por-pregunta` se hace una llamada por cada pregunta de la semana y el
promedio de las notas lo calcula el código. Es la forma de que cada pregunta
tenga su propia evaluación sin depender de que el modelo respete el formato.

Se le pueden dar dos prompts para comparar cómo cambia el mismo modelo con
cada uno, y `--muestra N` para tomar N respuestas por semestre, las mismas en
ambas pasadas:

    python -m modulos.tests.experimento --local --modelo in5162-qwen3-5-4b \\
        --historico --prompt experimentos/prompts/antiguo.md \\
        --prompt experimentos/prompts/nuevo.md --muestra 150

**No manda un solo correo, no toca `notas.csv` y no escribe en el log.** La nota
del alumno es la que se le comunicó; esto es un ensayo aparte y su resultado
vive en un CSV propio. Lo único que gasta es API.

El muestreo es aleatorio con semilla (`--semilla`, 19 por defecto), así que dos
corridas con la misma semilla eligen las mismas respuestas: es lo que permite
comparar dos prompts candidatos sobre la misma muestra en vez de sobre dos
muestras distintas.
"""

import csv
import random
import sys
from datetime import datetime
from pathlib import Path

from modulos import datos as _datos
from modulos.datos import reportes as _reportes

from . import config
from .evaluar import extraer_nota_y_originalidad
from .ia_prompts import evaluar_respuesta
from .preguntas import cargar_semana

SEMILLA_DEFAULT = 19
N_DEFAULT = 20

OLLAMA = "http://127.0.0.1:11434/v1"

COLUMNAS = [
    "Semestre", "Correo", "Nombre", "Semana", "Grupo",
    "NotaAntes", "NotaDespues", "DeltaNota",
    "OriginalidadAntes", "OriginalidadDespues", "DeltaNivel",
    "ModeloAntes", "ModeloDespues", "TokensEntrada", "TokensSalida",
    "Segundos", "FormatoOK",
    "Respuesta", "EvaluacionNueva",
    "EvaluacionAntes",  # la corrección que se le mandó, para leerla al lado de la nueva
]


def _anunciar_semestre() -> str:
    from modulos import semestre as _sem
    sid = _sem.activo_o_error()
    print(f"[EXPERIMENTO] semestre {sid}")
    return sid


def candidatas(semana: int | None = None, semestre_id: str | None = None) -> list[dict]:
    """Las casillas reevaluables: tienen el texto del alumno y una nota puesta.

    Sale del mismo `panel()` que alimenta la reportería, así que "lo que se
    evaluó" significa exactamente lo mismo acá que en los gráficos.
    """
    filas = _reportes.filtrar(_reportes.panel(semestre_id, _datos.TESTS))
    elegibles = [f for f in filas
                 if f["Respuesta"].strip() and f["Nota"] is not None]
    if semana is not None:
        elegibles = [f for f in elegibles if f["Item"] == str(semana)]
    return elegibles


def muestrear(filas: list[dict], n: int, semilla: int) -> list[dict]:
    """N casillas al azar, reproducible. Si se piden más de las que hay, van todas."""
    if n >= len(filas):
        return list(filas)
    return random.Random(semilla).sample(filas, n)


def _comparar(fila: dict, nota_nueva: str, originalidad_nueva: str) -> dict:
    """Las diferencias de una casilla entre la evaluación original y la nueva."""
    antes = fila["Nota"]
    despues = _reportes.nota_a_float(nota_nueva)
    nivel_antes = _reportes.nivel_originalidad(fila["Originalidad"])
    nivel_despues = _reportes.nivel_originalidad(originalidad_nueva)
    return {
        "NotaDespues": despues,
        "DeltaNota": (round(despues - antes, 2)
                      if despues is not None and antes is not None else None),
        "DeltaNivel": (nivel_despues - nivel_antes
                       if nivel_despues is not None and nivel_antes is not None else None),
    }


def _signos(valores: list) -> tuple[int, int, int]:
    """Cuántos subieron, bajaron y quedaron igual, ignorando los que no se pudo comparar."""
    limpios = [v for v in valores if v is not None]
    return (sum(1 for v in limpios if v > 0),
            sum(1 for v in limpios if v < 0),
            sum(1 for v in limpios if v == 0))


def _distribuciones(resultados: list[dict]) -> list[dict]:
    """Distribución de originalidad antes y después, sobre la misma muestra.

    Se arma con `distribucion_originalidad` en vez de contar acá: es la misma
    función que usa la reportería, así que los porcentajes se calculan igual.
    """
    antes = {d["Originalidad"].lower(): d for d in _reportes.distribucion_originalidad(
        [{"Originalidad": r["OriginalidadAntes"]} for r in resultados])}
    despues = {d["Originalidad"].lower(): d for d in _reportes.distribucion_originalidad(
        [{"Originalidad": r["OriginalidadDespues"]} for r in resultados])}

    etiquetas = sorted(
        set(antes) | set(despues),
        key=lambda e: (_reportes.nivel_originalidad(e) or 99, e),
    )
    return [{
        "Originalidad": e.title(),
        "Antes": antes.get(e, {}).get("Evaluaciones", 0),
        "AntesPct": antes.get(e, {}).get("Porcentaje", 0.0) or 0.0,
        "Despues": despues.get(e, {}).get("Evaluaciones", 0),
        "DespuesPct": despues.get(e, {}).get("Porcentaje", 0.0) or 0.0,
    } for e in etiquetas]


def _imprimir_comparacion(resultados: list[dict]) -> None:
    notas_antes = [r["NotaAntes"] for r in resultados if r["NotaAntes"] is not None]
    notas_despues = [r["NotaDespues"] for r in resultados if r["NotaDespues"] is not None]
    deltas = [r["DeltaNota"] for r in resultados]
    niveles = [r["DeltaNivel"] for r in resultados]

    print("\n=== NOTAS ===")
    if notas_antes:
        print(f"  media antes:   {sum(notas_antes) / len(notas_antes):.2f}")
    if notas_despues:
        print(f"  media después: {sum(notas_despues) / len(notas_despues):.2f}")
    sube, baja, igual = _signos(deltas)
    print(f"  subieron {sube}, bajaron {baja}, iguales {igual}")

    print("\n=== ORIGINALIDAD ===")
    sube, baja, igual = _signos(niveles)
    print(f"  subieron {sube}, bajaron {baja}, iguales {igual}")
    print(f"  {'categoría':12s} {'antes':>14s} {'después':>14s}")
    for d in _distribuciones(resultados):
        print(f"  {d['Originalidad']:12s} "
              f"{d['Antes']:5d} ({d['AntesPct']:4.1f}%) "
              f"{d['Despues']:5d} ({d['DespuesPct']:4.1f}%)")

    # La correlación se recalcula sobre la muestra reevaluada con las dos
    # etiquetas, para ver si el prompt nuevo separa mejor o peor la
    # originalidad de la nota.
    for cuando, orig, nota in (("antes", "OriginalidadAntes", "NotaAntes"),
                               ("después", "OriginalidadDespues", "NotaDespues")):
        c = _reportes.correlacion_originalidad_nota(
            [{"Originalidad": r[orig], "Nota": r[nota]} for r in resultados])
        print(f"  correlación originalidad–nota ({cuando}): "
              f"{'—' if c['R'] is None else c['R']}  (n={c['N']})")


def _escribir_csv(resultados: list[dict], destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
        w.writeheader()
        w.writerows(resultados)
    return destino


def _ya_hechas(destino: Path) -> list[dict]:
    """Lo que una corrida anterior ya dejó en ese archivo."""
    if not destino.exists():
        return []
    with destino.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _agregar_fila(fila: dict, destino: Path) -> None:
    """Escribe una fila apenas se obtiene.

    Una corrida contra un modelo local puede durar la noche entera. Si el CSV se
    escribiera al final, un corte de luz a las 6 AM perdería todo lo hecho.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    nuevo = not destino.exists()
    with destino.open("a", encoding="utf-8-sig" if nuevo else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
        if nuevo:
            w.writeheader()
        w.writerow(fila)


def _evaluar_por_pregunta(grupo_info, respuesta: str, plantilla: str):
    """Una llamada al modelo por cada pregunta de la semana, y el promedio acá.

    Pedirle al modelo que evalúe dos preguntas en un mismo mensaje y que
    entregue un bloque por cada una depende de que obedezca esa instrucción, y
    los modelos chicos las funden: en la corrida con qwen3.5:4b pasó en el 96%
    de las semanas con dos preguntas. Al fundirlas, el alumno recibe un juicio
    global en vez de uno por pregunta, y la nota solo puede ser entera, porque
    sale de un único puntaje sobre 3.

    Separando las llamadas, el bloque por pregunta queda garantizado por
    construcción y el promedio lo hace el código, no el modelo.
    """
    from modulos.datos import reportes as _rep

    htmls, notas, niveles = [], [], []
    tokens_in = tokens_out = 0
    modelo = ""

    # El estudiante responde todas las preguntas en un mismo correo, pero cada
    # llamada ve una sola. Sin esta aclaración el modelo descuenta puntaje por
    # "incluir contenido irrelevante", que es la respuesta a la otra pregunta.
    aclaracion = (
        "\n\nEVALUACIÓN PARCIAL: arriba hay UNA sola pregunta, pero el texto del "
        "estudiante puede contener además sus respuestas a las otras preguntas de "
        "la misma semana. Evalúa únicamente la parte que corresponde a la pregunta "
        "de arriba e ignora el resto. Nunca descuentes puntaje porque el texto "
        "incluya contenido de otra pregunta, ni lo llames irrelevante o fuera de "
        "tema: no es un defecto de su respuesta."
    )

    for i, (pregunta, pauta) in enumerate(zip(grupo_info.preguntas, grupo_info.pautas), 1):
        cuerpo = plantilla + (aclaracion if len(grupo_info.preguntas) > 1 else "")
        html = evaluar_respuesta([pregunta], [pauta], respuesta, plantilla=cuerpo)
        meta = getattr(html, "meta", {}) or {}
        modelo = meta.get("modelo") or modelo
        tokens_in += meta.get("prompt_tokens") or 0
        tokens_out += meta.get("completion_tokens") or 0

        nota, orig = extraer_nota_y_originalidad(html)
        n = _rep.nota_a_float(nota)
        if n is not None:
            notas.append(n)
        nivel = _rep.nivel_originalidad(orig)
        if nivel:
            niveles.append(nivel)
        etiqueta = f"<p><u>P{i}</u></p>" if len(grupo_info.preguntas) > 1 else ""
        htmls.append(etiqueta + str(html))

    nota_final = f"{sum(notas) / len(notas):.1f}".replace(".", ",") if notas else ""
    # La originalidad es un juicio sobre el texto completo, no sobre cada
    # pregunta: se toma el nivel medio de lo que dijo en cada llamada.
    orig_final = ""
    if niveles:
        medio = round(sum(niveles) / len(niveles))
        orig_final = _rep.ORDEN_ORIGINALIDAD[min(max(medio, 1), 5) - 1].title()

    return ("\n<hr>\n".join(htmls), nota_final, orig_final,
            {"modelo": modelo, "prompt_tokens": tokens_in, "completion_tokens": tokens_out})


def _numero(v):
    """Los valores que vuelven de un CSV anterior llegan como texto."""
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return _reportes.nota_a_float(v)


def _desde_csv(fila: dict) -> dict:
    fila = dict(fila)
    for k in ("NotaAntes", "NotaDespues", "DeltaNota"):
        fila[k] = _numero(fila.get(k))
    d = _numero(fila.get("DeltaNivel"))
    fila["DeltaNivel"] = int(d) if d is not None else None
    return fila


def _configurar_modelo(modelo: str | None, servidor: str | None, local: bool,
                       razonamiento: str | None = None) -> str:
    """Cambia el modelo solo para este proceso. No toca el .env."""
    from modulos import ia

    if local:
        servidor = servidor or OLLAMA
    if servidor or modelo:
        ia.configurar(
            (lambda: "ollama") if servidor else config.cargar_api_key,
            modelo=modelo or config.MODELO,
            servidor=servidor or "",
            # Un modelo local repartido entre GPU y RAM puede tardar minutos
            # por respuesta; el timeout por defecto del cliente lo cortaría.
            timeout=1800 if servidor else None,
            # En local el razonamiento se apaga salvo que se pida: multiplica
            # el tiempo por veinte y, con el tope de tokens, deja la respuesta
            # vacía. Contra OpenAI no se manda nada si no se pide.
            razonamiento=razonamiento or ("none" if servidor else ""),
        )
    return ia.ajustes()["modelo"]


def main(prompt: Path | None = None, n: int = N_DEFAULT, semana: int | None = None,
         semilla: int = SEMILLA_DEFAULT, dry_run: bool = False,
         salida: Path | None = None, modelo: str | None = None,
         servidor: str | None = None, local: bool = False,
         todas: bool = False, razonamiento: str | None = None,
         por_pregunta: bool = False) -> list[dict]:
    import time

    semestre_id = _anunciar_semestre()
    nombre_modelo = _configurar_modelo(modelo, servidor, local, razonamiento)
    donde = f"  ({servidor or OLLAMA})" if (servidor or local) else ""
    print(f"Modelo: {nombre_modelo}{donde}")

    # Sin --prompt se usa el vigente del semestre: es lo que corresponde cuando
    # lo que se compara es el modelo y no el prompt.
    prompt = Path(prompt) if prompt else config.PROMPTS / "evaluar_respuesta.md"
    plantilla = prompt.read_text(encoding="utf-8")
    print(f"Prompt: {prompt}")
    if "{{PREGUNTAS}}" not in plantilla or "{{PAUTAS}}" not in plantilla:
        print("⚠ El prompt no tiene {{PREGUNTAS}} ni {{PAUTAS}}: el modelo va a "
              "evaluar sin ver la pregunta ni la pauta.")
    if "NOTA FINAL" not in plantilla or "ORIGINALIDAD" not in plantilla:
        print("⚠ El prompt no menciona 'NOTA FINAL:' ni 'ORIGINALIDAD:'. Sin esas "
              "etiquetas no se puede leer el resultado y la comparación sale vacía.")

    disponibles = candidatas(semana)
    ambito = f"semana {semana}" if semana is not None else "todas las semanas"
    print(f"Respuestas ya evaluadas ({ambito}): {len(disponibles)}")
    if not disponibles:
        print("No hay nada que reevaluar.")
        return []

    muestra = list(disponibles) if todas else muestrear(disponibles, n, semilla)
    print(f"A reevaluar: {len(muestra)}" + ("" if todas else f" (semilla {semilla})"))

    if salida is None:
        marca = datetime.now().strftime("%Y%m%d-%H%M%S")
        salida = config.DATA / f"experimento_{marca}.csv"
    salida = Path(salida)

    previas = _ya_hechas(salida)
    hechas = {(r.get("Correo", ""), str(r.get("Semana", ""))) for r in previas}
    pendientes = [f for f in muestra if (f["Correo"], f["Item"]) not in hechas]
    if previas:
        print(f"Retomando {salida.name}: {len(previas)} ya hechas, faltan {len(pendientes)}")
    print()

    if not dry_run and not (servidor or local):
        # La key se pedía recién dentro del loop, una vez por respuesta: quien
        # no la tenía configurada veía N errores iguales y un "no se pudo
        # reevaluar ninguna" al final, sin decir que faltaba la key.
        try:
            config.cargar_api_key()
        except Exception as e:  # noqa: BLE001
            print(f"No puedo llamar al modelo: {e}")
            print("\nLa API key va en el archivo .env de la raíz del proyecto, que "
                  "no viaja ni por git ni en el zip del semestre: cada equipo arma "
                  "el suyo copiando .env.example. Sin eso no se puede reevaluar.")
            return []

    if dry_run:
        # Lo que se lista son las notas que ya tienen puestas, no un resultado
        # del prompt candidato. Sin decirlo, la salida se lee como si el prompt
        # nuevo no hubiera cambiado nada, que es la confusión que motivó esto.
        print("MODO PRUEBA: esta es la muestra que se reevaluaría, con la nota "
              "que ya tiene cada uno.")
        print("El prompt candidato todavía NO se usó.\n")
        for f in pendientes:
            print(f"-> {f['Nombre']:30s} semana {f['Item']:>3s}  nota actual "
                  f"{f['NotaTexto'] or '?'}, originalidad {f['Originalidad'] or '?'}")
        print(f"\nNo se llamó al modelo, así que no hay nada que comparar. "
              f"Serían {len(pendientes)} llamadas.")
        print("Para probarlo de verdad, apaga «Solo mostrar la muestra» en la "
              "app, o quita --dry-run en la terminal.")
        return []

    semanas: dict[int, object] = {}
    fallidas = 0
    inicio_total = time.time()

    for i, fila in enumerate(pendientes, start=1):
        etiqueta = f"{fila['Nombre'][:28]:28s} sem {fila['Item']:>3s}"
        try:
            num = int(fila["Item"])
        except ValueError:
            fallidas += 1
            print(f"✗ {etiqueta}: ítem no numérico, no puedo cargar sus preguntas")
            continue

        if num not in semanas:
            try:
                semanas[num] = cargar_semana(num)
            except Exception as e:  # noqa: BLE001
                semanas[num] = None
                print(f"⚠ semana {num}: {e}")
        info = semanas[num]
        if info is None:
            fallidas += 1
            continue

        grupo_info = info.para_grupo(fila["Grupo"] or "control")

        t0 = time.time()
        try:
            if por_pregunta:
                html, nota_nueva, orig_nueva, meta = _evaluar_por_pregunta(
                    grupo_info, fila["Respuesta"], plantilla)
            else:
                html = evaluar_respuesta(grupo_info.preguntas, grupo_info.pautas,
                                         fila["Respuesta"], plantilla=plantilla)
                nota_nueva, orig_nueva = extraer_nota_y_originalidad(html)
                meta = getattr(html, "meta", {}) or {}
        except Exception as e:  # noqa: BLE001
            fallidas += 1
            print(f"✗ {etiqueta}: error del modelo: {e}", flush=True)
            continue
        segundos = round(time.time() - t0, 1)
        comparacion = _comparar(fila, nota_nueva, orig_nueva)

        registro = {
            "Semestre": semestre_id,
            "Correo": fila["Correo"],
            "Nombre": fila["Nombre"],
            "Semana": fila["Item"],
            "Grupo": fila["Grupo"],
            "NotaAntes": fila["Nota"],
            "OriginalidadAntes": fila["Originalidad"],
            "OriginalidadDespues": orig_nueva,
            "ModeloAntes": fila["Modelo"],
            "ModeloDespues": meta.get("modelo") or nombre_modelo,
            "TokensEntrada": meta.get("prompt_tokens") or "",
            "TokensSalida": meta.get("completion_tokens") or "",
            "Segundos": segundos,
            # Un modelo chico que no escribe "NOTA FINAL:" tal cual deja la nota
            # sin extraer. Se cuenta aparte porque en producción eso sería un
            # alumno sin nota, que es peor que una nota distinta.
            "FormatoOK": "SI" if nota_nueva else "NO",
            "Respuesta": fila["Respuesta"],
            "EvaluacionNueva": str(html),
            "EvaluacionAntes": fila.get("EvaluacionIA", ""),
            **comparacion,
        }
        _agregar_fila(registro, salida)

        transcurrido = time.time() - inicio_total
        restante = transcurrido / i * (len(pendientes) - i)
        flecha = ("=" if comparacion["DeltaNivel"] in (0, None)
                  else "↑" if comparacion["DeltaNivel"] > 0 else "↓")
        print(f"✓ [{i}/{len(pendientes)}] {etiqueta}: "
              f"nota {fila['NotaTexto'] or '?'} → {nota_nueva or 'SIN NOTA'}, "
              f"originalidad {fila['Originalidad'] or '?'} → {orig_nueva or '?'} {flecha}"
              f"   {segundos:.0f}s  (faltan ~{restante / 60:.0f} min)", flush=True)

    resultados = [_desde_csv(r) for r in _ya_hechas(salida)]
    if not resultados:
        print("\nNo se pudo reevaluar ninguna respuesta.")
        return []

    _imprimir_comparacion(resultados)
    sin_formato = sum(1 for r in resultados if r.get("FormatoOK") == "NO")
    print(f"\n  sin nota legible (formato roto): {sin_formato} de {len(resultados)}")

    print(f"\nReevaluadas: {len(resultados)}  Fallidas en esta corrida: {fallidas}")
    print(f"Detalle: {salida}")
    return resultados


def _no_suspender(activo: bool) -> None:
    """Pide a Windows que no suspenda el equipo mientras dure la corrida.

    Una corrida de toda la noche se congela si el PC se duerme a las 2 AM, y a
    la mañana solo se ve que avanzó dos horas. Vale únicamente mientras este
    proceso vive: al terminar, el equipo vuelve a su configuración normal.
    """
    if sys.platform != "win32":
        return
    import ctypes

    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    estado = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if activo else 0)
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(estado)
    except Exception:  # noqa: BLE001
        print("⚠ No pude impedir la suspensión: revisa que el PC no se duerma.")


def _archivo_historico(semestre_id: str, modelo: str, prompt: Path | None = None) -> Path:
    """Dónde queda el resultado. El nombre lleva el modelo y el prompt usado.

    Así dos pasadas con prompts distintos no se pisan, y cada una se puede
    retomar por separado si se corta.
    """
    from modulos import semestre as _sem

    etiqueta = modelo + (f"__{Path(prompt).stem}" if prompt else "")
    limpio = "".join(c if c.isalnum() or c in "-_." else "_" for c in etiqueta)
    return _sem.raiz(semestre_id) / "experimentos" / f"{limpio}.csv"


def _resumen_historico(archivos: list[Path]) -> None:
    """Cuánto coincide el modelo con lo que se les puso a los alumnos."""
    filas = []
    for a in archivos:
        filas += [_desde_csv(r) for r in _ya_hechas(a)]
    if not filas:
        print("No hay resultados que resumir.")
        return

    con_nota = [f for f in filas if f["NotaAntes"] is not None and f["NotaDespues"] is not None]
    deltas = [abs(f["NotaDespues"] - f["NotaAntes"]) for f in con_nota]
    iguales = sum(1 for d in deltas if d < 0.05)
    cerca = sum(1 for d in deltas if d <= 0.5)
    niveles = [f["DeltaNivel"] for f in filas if f["DeltaNivel"] is not None]
    rotas = sum(1 for f in filas if f.get("FormatoOK") == "NO")
    segundos = [float(f["Segundos"]) for f in filas if f.get("Segundos")]

    print("\n=== RESUMEN DE TODOS LOS SEMESTRES ===")
    print(f"  respuestas reevaluadas:   {len(filas)}")
    print(f"  sin nota legible:         {rotas} ({rotas / len(filas):.1%})")
    if deltas:
        print(f"  nota idéntica:            {iguales} de {len(deltas)} ({iguales / len(deltas):.1%})")
        print(f"  a medio punto o menos:    {cerca} ({cerca / len(deltas):.1%})")
        print(f"  diferencia media (abs):   {sum(deltas) / len(deltas):.2f} puntos")
        medias = [f["NotaAntes"] for f in con_nota], [f["NotaDespues"] for f in con_nota]
        print(f"  nota media GPT → local:   {sum(medias[0]) / len(medias[0]):.2f} → "
              f"{sum(medias[1]) / len(medias[1]):.2f}")
    if niveles:
        igual = sum(1 for n in niveles if n == 0)
        sube = sum(1 for n in niveles if n > 0)
        print(f"  originalidad idéntica:    {igual} de {len(niveles)} ({igual / len(niveles):.1%}); "
              f"más alta en {sube}, más baja en {len(niveles) - igual - sube}")
    if segundos:
        print(f"  tiempo por respuesta:     {sum(segundos) / len(segundos):.0f} s en promedio")


def _contrastar(archivos_a: list[Path], archivos_b: list[Path],
                nombre_a: str, nombre_b: str) -> None:
    """Las dos pasadas, respuesta por respuesta, sobre las casillas que tienen ambas.

    Es la comparación que aísla el efecto del prompt: mismo modelo, misma
    respuesta del alumno, solo cambia el prompt.
    """
    def indice(archivos):
        d = {}
        for a in archivos:
            for r in _ya_hechas(a):
                d[(r.get("Semestre"), r.get("Correo"), str(r.get("Semana")))] = _desde_csv(r)
        return d

    a, b = indice(archivos_a), indice(archivos_b)
    comunes = sorted(set(a) & set(b))
    print(f"\n=== {nombre_a} vs {nombre_b}, mismo modelo ===")
    print(f"  respuestas con las dos pasadas: {len(comunes)}")
    if not comunes:
        return

    for nombre, d in ((nombre_a, a), (nombre_b, b)):
        notas = [d[k]["NotaDespues"] for k in comunes if d[k]["NotaDespues"] is not None]
        niveles = [_reportes.nivel_originalidad(d[k].get("OriginalidadDespues"))
                   for k in comunes]
        niveles = [n for n in niveles if n]
        rotas = sum(1 for k in comunes if d[k].get("FormatoOK") == "NO")
        print(f"  {nombre:10s} nota media {sum(notas) / len(notas) if notas else float('nan'):.2f}"
              f"   originalidad media {sum(niveles) / len(niveles) if niveles else float('nan'):.2f}"
              f"   sin nota {rotas}")

    pares = [(a[k]["NotaDespues"], b[k]["NotaDespues"]) for k in comunes
             if a[k]["NotaDespues"] is not None and b[k]["NotaDespues"] is not None]
    if pares:
        iguales = sum(1 for x, y in pares if abs(x - y) < 0.05)
        print(f"  la nota coincide entre los dos prompts en {iguales} de {len(pares)}"
              f" ({iguales / len(pares):.1%})")

    print(f"  originalidad ({nombre_a} → {nombre_b}):")
    cambios: dict = {}
    for k in comunes:
        clave = (a[k].get("OriginalidadDespues") or "?", b[k].get("OriginalidadDespues") or "?")
        cambios[clave] = cambios.get(clave, 0) + 1
    for (x, y), n in sorted(cambios.items(), key=lambda kv: -kv[1])[:12]:
        print(f"     {x:10s} → {y:10s} {n}")


def historico(modelo: str | None, servidor: str | None, local: bool,
              razonamiento: str | None, semana: int | None = None,
              prompts: list[Path] | None = None, muestra: int | None = None,
              semilla: int = SEMILLA_DEFAULT, por_pregunta: bool = False) -> None:
    """Corre cada prompt sobre cada semestre, uno por proceso.

    Cada semestre va en su propio proceso con IN5162_SEMESTRE, porque las rutas
    de preguntas y prompts se calculan al importar: cambiar de semestre dentro
    del mismo proceso seguiría leyendo las preguntas del anterior.

    El orden es por semestre y, dentro de cada uno, los prompts seguidos. Si la
    noche no alcanza, lo que quedó hecho tiene las dos versiones de cada
    respuesta y se puede comparar igual; al revés quedaría un prompt completo y
    el otro sin empezar.

    Con `muestra` se toman N respuestas por semestre con la semilla, las mismas
    para todos los prompts, en vez de todas.
    """
    import os
    import subprocess

    from modulos import semestre as _sem

    nombre = modelo or config.MODELO
    prompts = list(prompts or [None])

    # Si Ollama no está abierto, cada respuesta falla por separado y a la
    # mañana hay cientos de errores iguales. Mejor detenerse de entrada.
    if local or servidor:
        import urllib.request

        base = (servidor or OLLAMA).rstrip("/").removesuffix("/v1")
        try:
            urllib.request.urlopen(base + "/api/version", timeout=5).read()
        except Exception as e:  # noqa: BLE001
            print(f"No hay servidor de modelos en {base} ({e}).")
            print("Abre Ollama (queda como ícono junto al reloj) y vuelve a lanzar el comando.")
            return
    semestres = [x for x in _sem.listar() if not x.startswith("_")]
    archivos = {pr: [_archivo_historico(x, nombre, pr) for x in semestres] for pr in prompts}

    print(f"Corrida histórica con {nombre} sobre {', '.join(semestres)}")
    for pr in prompts:
        # Sin --prompt cada semestre usaría el suyo, y hoy no son todos iguales:
        # la comparación mezclaría dos versiones sin que se note.
        print(f"  prompt: {Path(pr).resolve() if pr else 'el de cada semestre'}")
    print(f"  {'muestra de ' + str(muestra) + ' por semestre' if muestra else 'todas las respuestas'}")
    print()

    _no_suspender(True)
    try:
        for i, x in enumerate(semestres):
            for pr in prompts:
                cmd = [sys.executable, "-m", "modulos.tests.experimento",
                       "--salida", str(archivos[pr][i])]
                cmd += (["-n", str(muestra), "--semilla", str(semilla)] if muestra
                        else ["--todas"])
                if modelo:
                    cmd += ["--modelo", modelo]
                if servidor:
                    cmd += ["--servidor", servidor]
                if local:
                    cmd.append("--local")
                if razonamiento:
                    cmd += ["--razonamiento", razonamiento]
                if semana is not None:
                    cmd += ["--semana", str(semana)]
                if pr:
                    cmd += ["--prompt", str(Path(pr).resolve())]
                if por_pregunta:
                    cmd.append("--por-pregunta")
                titulo_corrida = f"{x}  ·  prompt {Path(pr).stem if pr else 'del semestre'}"
                print(f"\n{'=' * 70}\n{titulo_corrida}\n{'=' * 70}", flush=True)
                subprocess.run(cmd, env={**os.environ, "IN5162_SEMESTRE": x})
    finally:
        _no_suspender(False)

    for pr in prompts:
        print(f"\n##### prompt {Path(pr).stem if pr else 'del semestre'} contra lo que puso GPT")
        _resumen_historico(archivos[pr])
    if len(prompts) == 2 and all(prompts):
        _contrastar(archivos[prompts[0]], archivos[prompts[1]],
                    Path(prompts[0]).stem, Path(prompts[1]).stem)


def _parsear_args(argv: list[str]) -> dict:
    opciones = {"prompt": None, "n": N_DEFAULT, "semana": None,
                "semilla": SEMILLA_DEFAULT, "dry_run": False, "salida": None,
                "modelo": None, "servidor": None, "local": False, "todas": False,
                "razonamiento": None, "historico": False, "por_pregunta": False,
                "prompts": [], "muestra": None}
    esperando = None

    for a in argv:
        if esperando:
            if esperando == "prompt":
                opciones["prompts"].append(a)
            opciones[esperando] = a
            esperando = None
        elif a in ("--prompt", "-p"):
            esperando = "prompt"
        elif a == "--muestra":
            esperando = "muestra"
        elif a in ("-n", "--n", "--cantidad"):
            esperando = "n"
        elif a in ("--semana", "-s"):
            esperando = "semana"
        elif a == "--semilla":
            esperando = "semilla"
        elif a in ("--salida", "-o"):
            esperando = "salida"
        elif a in ("--dry-run", "--dry"):
            opciones["dry_run"] = True
        elif a in ("--modelo", "-m"):
            esperando = "modelo"
        elif a == "--servidor":
            esperando = "servidor"
        elif a == "--razonamiento":
            esperando = "razonamiento"
        elif a == "--local":
            opciones["local"] = True
        elif a == "--todas":
            opciones["todas"] = True
        elif a == "--por-pregunta":
            opciones["por_pregunta"] = True
        elif a == "--historico":
            opciones["historico"] = True
        else:
            print(f"Argumento desconocido: {a}")
            print(__doc__)
            raise SystemExit(2)

    if esperando:
        print(f"Falta el valor de --{esperando}")
        raise SystemExit(2)

    if not opciones["prompt"] and not (opciones["modelo"] or opciones["local"]
                                       or opciones["servidor"]):
        print("Falta --prompt (para probar un prompt) o --modelo (para probar un modelo).")
        print(__doc__)
        raise SystemExit(2)

    if opciones["prompt"] is not None:
        opciones["prompt"] = Path(opciones["prompt"])
    if opciones["prompt"] is not None and not opciones["prompt"].exists():
        print(f"No existe el archivo de prompt: {opciones['prompt']}")
        raise SystemExit(2)

    for campo in ("n", "semilla"):
        opciones[campo] = int(opciones[campo])
    if opciones["semana"] is not None:
        opciones["semana"] = int(opciones["semana"])
    if opciones["salida"] is not None:
        opciones["salida"] = Path(opciones["salida"])

    return opciones


if __name__ == "__main__":
    _op = _parsear_args(sys.argv[1:])
    _prompts = [Path(x) for x in _op.pop("prompts")]
    _muestra = _op.pop("muestra")
    if _op.pop("historico"):
        historico(_op["modelo"], _op["servidor"], _op["local"], _op["razonamiento"],
                  _op["semana"], _prompts, int(_muestra) if _muestra else None,
                  _op["semilla"], _op["por_pregunta"])
    else:
        if len(_prompts) > 1:
            print("Varios --prompt solo tienen sentido con --historico.")
            raise SystemExit(2)
        main(**_op)
