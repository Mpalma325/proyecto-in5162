"""
Parseo y limpieza de cuerpos de correo.

Se toma como base la versión que vivía en tests_semanales, que es la más
completa: la de tareas cortaba el texto en el primer salto de linea seguido
de "El ", lo que mutilaba
cualquier respuesta que tuviera una línea empezando con "El " (por ejemplo
"El modelo de regresión...").
"""

import email
import re
from email.header import decode_header

# La línea con que un cliente de correo presenta la cita del mensaje original:
# "El vie, 25 sep 2026 a las 12:00, <in5162@uchile.cl> escribió:",
# "El El vie, …" (algunas apps del celular) u "On Fri, … wrote:".
# Los dos puntos son obligatorios: "El autor lo escribió" es una frase del alumno.
_ENCABEZADO_CITA = re.compile(r'^(?:El |On ).*(?:escribi[óo]|wrote)\s*:\s*$')
# La segunda mitad de un encabezado partido en dos líneas: "in5162@uchile.cl> escribió:".
_FIN_ENCABEZADO = re.compile(r'^(?!El |On ).*@.*(?:escribi[óo]|wrote)\s*:\s*$')


def _decodificar_header(raw: str) -> str:
    if not raw:
        return ""
    partes = decode_header(raw)
    resultado = []
    for texto, encoding in partes:
        if isinstance(texto, bytes):
            try:
                resultado.append(texto.decode(encoding or "utf-8", errors="replace"))
            except LookupError:
                resultado.append(texto.decode("utf-8", errors="replace"))
        else:
            resultado.append(texto)
    return "".join(resultado)


def _extraer_cuerpo(msg: email.message.Message) -> str:
    texto_plano = ""
    texto_html = ""

    if msg.is_multipart():
        for parte in msg.walk():
            ctype = parte.get_content_type()
            dispo = str(parte.get("Content-Disposition") or "")
            if "attachment" in dispo:
                continue
            try:
                payload = parte.get_payload(decode=True)
                if not payload:
                    continue
                decoded = payload.decode(parte.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                continue

            if ctype == "text/plain" and not texto_plano:
                texto_plano = decoded
            elif ctype == "text/html" and not texto_html:
                texto_html = decoded
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                decoded = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                if msg.get_content_type() == "text/html":
                    texto_html = decoded
                else:
                    texto_plano = decoded
        except Exception:
            pass

    if texto_plano.strip():
        return texto_plano

    if texto_html.strip():
        return _html_a_texto(texto_html)

    return ""


def _html_a_texto(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        import re
        texto = re.sub(r'<br\s*/?>', '\n', html)
        texto = re.sub(r'</(p|div|tr|li)>', '\n', texto)
        texto = re.sub(r'<[^>]+>', '', texto)
        return texto.strip()

    soup = BeautifulSoup(html, "html.parser")

    for quote in soup.select(".gmail_quote, .yahoo_quoted, blockquote"):
        quote.decompose()

    for tag in soup.find_all(["style", "script"]):
        tag.decompose()

    return soup.get_text("\n", strip=True)


def _recuperar_de_la_cita(lineas: list) -> str:
    """Texto del alumno escrito DENTRO del bloque citado.

    Hay quien responde debajo de cada pregunta, dentro de la cita: sus líneas
    quedan con '>' delante y se descartarían como si fueran del correo
    original. Se sacan las marcas y se limpia de nuevo, que ahora corta por el
    'El ... escribió:' y deja fuera la pregunta.
    """
    import re
    sin_marcas = chr(10).join(re.sub(r'^\s*>+ ?', '', l) for l in lineas)
    return _limpiar_respuesta(sin_marcas, _descitado=True).strip()


def _limpiar_respuesta(texto: str, _descitado: bool = False) -> str:
    import re

    # Los correos llegan con fines de línea de Windows (\r\n). Con el \r
    # colgando, los patrones que terminan en fin de línea no calzan.
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    lineas = texto.split('\n')

    es_citada = [l.lstrip().startswith(">") for l in lineas]
    n_citadas = sum(es_citada)

    if n_citadas >= 2:
        primera_cita = next(i for i, c in enumerate(es_citada) if c)
        ultima_cita = max(i for i, c in enumerate(es_citada) if c)

        # El encabezado "El … escribió:" va justo antes de la cita, a veces con
        # una línea en blanco de por medio (así lo dejan algunas apps del
        # celular) o partido en dos líneas. Mirar solo la línea anterior lo
        # dejaba pegado a la respuesta.
        fin_antes = primera_cita
        j = fin_antes - 1
        while j >= 0 and not lineas[j].strip():
            j -= 1
        if j >= 0 and _ENCABEZADO_CITA.match(lineas[j].strip()):
            fin_antes = j
        elif j >= 1 and _ENCABEZADO_CITA.match(f"{lineas[j - 1].strip()} {lineas[j].strip()}"):
            fin_antes = j - 1

        texto_antes = "\n".join(lineas[:fin_antes]).strip()
        texto_despues = "\n".join(lineas[ultima_cita + 1:]).strip()

        # Respondió intercalado: su texto va entre bloques citados, debajo de
        # cada pregunta. Quedarse solo con lo de arriba o lo de abajo perdía
        # respuestas; se toma todo lo que no es cita.
        intercalado = any(lineas[i].strip() and not es_citada[i]
                          for i in range(primera_cita, ultima_cita))
        if intercalado:
            return _limpiar_lineas(_sin_cita("\n".join(lineas)))

        if len(texto_despues) > len(texto_antes):
            return _limpiar_lineas(texto_despues)
        elif texto_antes:
            # Puede ser solo un saludo ('Hola, mis respuestas:') con las
            # respuestas de verdad escritas dentro de la cita. Si al sacar
            # las marcas aparece mucho más texto, ese es el bueno.
            arriba = _limpiar_lineas(texto_antes)
            adentro = _recuperar_de_la_cita(lineas)
            if len(adentro) > 2 * len(arriba) + 300:
                return adentro
            return arriba

        # No hay nada fuera de la cita. Hay alumnos que responden intercalando
        # su texto DENTRO del bloque citado, debajo de cada pregunta: sus líneas
        # también empiezan con '>', y descartarlas deja la respuesta vacía.
        # Se quitan las marcas de cita y se vuelve a limpiar, que ahora corta
        # por el 'El ... escribió:' si es que aparece.
        if not _descitado:
            recuperado = _recuperar_de_la_cita(lineas)
            if recuperado:
                return recuperado

        return _limpiar_lineas(texto_despues)

    marcadores_fijos = [
        "\n-----Mensaje original-----",
        "\n-----Original Message-----",
        "\n________________________________",
    ]
    patrones_regex = [
        # Gmail español: "El lun, 4 may 2026". Algunas apps del celular repiten
        # el "El" ("El El vie, 25 sep. 2026 a la(s) 12:00, … escribió:"), y sin
        # el (?:El )+ la cita completa quedaba pegada a la respuesta.
        r'\n(?:El )+\w{3},?\s+\d{1,2}\s+\w{3,4}\.?\s+\d{4}',
        r'\nOn \w{3},?\s+\w{3,4}\.?\s+\d{1,2},?\s+\d{4}',        # Gmail inglés
        r'\nEl \d{2}-\d{2}-\d{4},? a las',                       # Apple Mail español: "El 29-05-2026, a las"
        # Cualquier otro encabezado de cita: una línea que empieza con "El " u
        # "On ", trae el correo del remitente (@) y termina en "escribió:" /
        # "wrote:". También partida en dos líneas (nombre del remitente largo),
        # pero la segunda no puede empezar con "El "/"On ": si no, una línea
        # del alumno que empieza con "El" se tomaba como parte del encabezado.
        r'\n(?:El |On )[^\n]{0,200}?@[^\n]{0,120}?(?:escribi[óo]|wrote)\s*:[ \t]*(?=\n|$)',
        r'\n(?:El |On )[^\n]{0,200}?\n(?!El |On )[^\n]{0,120}?@[^\n]{0,120}?'
        r'(?:escribi[óo]|wrote)\s*:[ \t]*(?=\n|$)',
    ]

    idx_corte = len(texto)
    for m in marcadores_fijos:
        i = texto.find(m)
        if 0 <= i < idx_corte:
            idx_corte = i
    for patron in patrones_regex:
        m = re.search(patron, texto)
        if m and m.start() < idx_corte:
            idx_corte = m.start()

    antes = _limpiar_lineas(texto[:idx_corte])
    despues = _limpiar_lineas(_sin_cita(texto[idx_corte:]))

    # Lo normal es responder ARRIBA de la cita. Solo si lo de arriba está vacío
    # o es un mero saludo ("Hola,", "Mis respuestas en azul:") se asume que el
    # alumno escribió debajo.
    if antes and not _es_solo_saludo(antes):
        return antes
    return despues or antes


def _limpiar_lineas(texto: str) -> str:
    lineas = [l.rstrip() for l in texto.splitlines()]
    return "\n".join(lineas).strip()


_SALUDOS = re.compile(
    r'^(hola|buenas|buenos d[ií]as|buenas tardes|estimad[oa]s?|cordial saludo|'
    r'saludos|profe(sor)?|mis? respuestas?|respuestas?|en azul|adjunto)',
    re.IGNORECASE,
)


def _es_solo_saludo(texto: str) -> bool:
    """True si lo escrito arriba de la cita es apenas un encabezado."""
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    if not lineas or len(texto) > 120:
        return False
    return all(_SALUDOS.match(l) or len(l) <= 3 for l in lineas)


def _sin_cita(texto: str) -> str:
    """Quita las líneas citadas y el encabezado 'El ... escribió:', también partido en dos."""
    fuera = []
    for linea in texto.splitlines():
        limpia = linea.lstrip()
        if limpia.startswith(">"):
            continue
        if _ENCABEZADO_CITA.match(limpia.strip()):
            continue
        # Segunda mitad de un encabezado partido: se va junto con la primera.
        if (_FIN_ENCABEZADO.match(limpia.strip()) and fuera
                and re.match(r'^(?:El |On )', fuera[-1].strip())):
            fuera.pop()
            continue
        fuera.append(linea)
    return chr(10).join(fuera)
