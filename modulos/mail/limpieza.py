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


def _adjuntos(msg: email.message.Message) -> list[str]:
    """Los nombres de los archivos adjuntos. No se leen: sirven para avisar que venían."""
    nombres = []
    for parte in msg.walk():
        if parte.is_multipart():
            continue
        if "attachment" in str(parte.get("Content-Disposition") or "").lower():
            nombres.append(_decodificar_header(parte.get_filename() or "") or parte.get_content_type())
    return nombres


def _recuperar_de_la_cita(lineas: list) -> str:
    """Texto del alumno escrito DENTRO del bloque citado.

    Hay quien responde debajo de cada pregunta, dentro de la cita: sus líneas
    quedan con '>' delante y se descartarían como si fueran del correo
    original. Se sacan las marcas y se limpia de nuevo, que ahora corta por el
    'El ... escribió:' y deja fuera la pregunta.

    Si el alumno no escribió nada, lo recuperado es el correo original entero.
    Sin ese correo no hay cómo distinguir un caso del otro: quien lo tiene lo
    revisa con `es_solo_eco` (Tareas, en recolectar).
    """
    import re
    sin_marcas = chr(10).join(re.sub(r'^\s*>+ ?', '', l) for l in lineas)
    return _descitar(sin_marcas, _descitado=True).strip()


def _descitar(texto: str, _descitado: bool = False) -> str:
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


def _limpiar_respuesta(texto: str) -> str:
    """Lo que escribió el alumno: sin la cita del correo original, el saludo ni la firma."""
    return _sin_saludo_ni_firma(_descitar(texto))


def _normal_eco(linea: str) -> str:
    """Una línea para comparar con el correo enviado: sin marcas de cita ni espacios de más."""
    linea = re.sub(r"^\s*(?:>\s*)+", "", linea.replace("\xa0", " "))
    return " ".join(linea.split()).casefold()


def es_solo_eco(texto: str, plantilla: str, valores: dict) -> bool:
    """
    ¿Todo lo que queda de la respuesta venía en el correo que se le envió?

    Quien responde sin escribir nada deja solo la cita, y `_descitar` la toma
    por una respuesta escrita dentro de ella: quedaba registrada como respuesta
    nuestra propia pregunta (prueba de Tareas del 19/11/2026, 8 de 8 casos).
    Con el correo enviado a la vista sí se distingue: si ninguna línea es del
    alumno, la respuesta está vacía.

    `plantilla` es la del correo, con sus {campos}; los de `valores` se
    reemplazan y los demás (los minutos, por ejemplo) calzan con cualquier
    texto corto. Una línea es eco si es una línea entera del correo, o un trozo
    de cuatro palabras o más de él, o el encabezado "El … escribió:". Hay
    clientes que cortan las líneas largas al citar: por eso también se compara
    cada párrafo entero (las líneas seguidas, sin una en blanco entre ellas).
    Solo dice si TODO es eco: una respuesta con una sola línea propia se deja
    entera, como antes.
    """
    parrafos = [[l for l in p.splitlines() if _normal_eco(l)]
                for p in re.split(r"\n\s*(?:>\s*)*\n", (texto or "").replace("\r\n", "\n"))]
    parrafos = [p for p in parrafos if p]
    if not parrafos:
        return False

    comodin = "\x00"
    enviado = re.sub(r"\{(\w+)\}",
                     lambda m: str(valores[m.group(1)]) if valores.get(m.group(1)) is not None else comodin,
                     (plantilla or "").replace("\r\n", "\n"))
    normales = [_normal_eco(l) for l in enviado.splitlines()]
    # Las líneas y los párrafos del correo enviado.
    piezas = normales + [" ".join(_normal_eco(l) for l in p.splitlines()).strip()
                         for p in re.split(r"\n\s*\n", enviado)]
    enteras = {l for l in piezas if l and comodin not in l}
    # Las que tienen un campo desconocido calzan como patrón, si les queda texto
    # fijo suficiente: "Tienes {minutos} minutos…" sí, "{nombre}:" no.
    patrones = [re.compile(".{1,80}?".join(re.escape(t) for t in l.split(comodin)))
                for l in piezas
                if comodin in l and len(re.sub(r"\W", "", l.replace(comodin, ""))) >= 4]
    trozos = " ".join(normales).split(comodin)

    def eco(linea: str) -> bool:
        return (linea in enteras
                or any(p.fullmatch(linea) for p in patrones)
                or (len(linea.split()) >= 4 and any(linea in t for t in trozos)))

    def encabezado(original: str) -> bool:
        sin_marcas = re.sub(r"^\s*(?:>\s*)+", "", original).strip()
        return bool(_ENCABEZADO_CITA.match(sin_marcas) or _FIN_ENCABEZADO.match(sin_marcas))

    return all(eco(" ".join(_normal_eco(l) for l in p))
               or all(eco(_normal_eco(l)) or encabezado(l) for l in p)
               for p in parrafos)


# Idea tomada del limpiador de Renzo (socrates): quitar saludo y firma. Pero
# solo líneas que son ENTERAS un saludo o una firma; si la línea sigue con
# contenido ("Hola, era necesario para…") se deja, que es donde el suyo perdía
# parte de la respuesta.
_LINEA_SALUDO = re.compile(
    r"^(hola|holi|buen[oa]s?( (d[ií]as|tardes|noches))?|estimad[oa]s?\b[^,:!.]{0,40}|"
    r"junto con saludar|espero que est[eé]n? bien)[\s,!.:;c]*$",
    re.IGNORECASE,
)
# "Mis respuestas son las siguientes:", "Adjunto mi respuesta c:", "envío aquí mis respuestas:".
# Solo la presentación, sin nada más: "Respuesta: sí, porque…" es una respuesta y se queda.
_LINEA_PRESENTACION = re.compile(
    r"^((hola|buen[oa]s?( (d[ií]as|tardes))?)[\s,!.]*)?"
    r"((ac[aá]|aqu[ií]) van|adjunto|env[ií]o( aqu[ií])?|les? env[ií]o|les dejo|estas son|a continuaci[oó]n)?\s*"
    r"(mis|mi|las)?\s*respuestas?"
    r"( a (las|la|estas) preguntas?| de (esta|la) semana| son las siguientes| son| es la siguiente)*"
    r"\s*[:.]?\s*(c:)?$",
    re.IGNORECASE,
)
_LINEA_FIRMA = re.compile(
    r"^(saludos( cordiales)?|cordiales saludos|atte\.?|atentamente|slds\.?|"
    r"(muchas )?gracias( de antemano)?|quedo atent[oa]\.?|enviado desde mi [\w ]{2,20})[\s,!.]*$",
    re.IGNORECASE,
)


def _sin_saludo_ni_firma(texto: str) -> str:
    lineas = texto.split("\n")
    # Arriba: hasta dos líneas de saludo o de presentación ("Mis respuestas son:").
    for _ in range(2):
        primera = next((i for i, l in enumerate(lineas) if l.strip()), None)
        if primera is None:
            break
        l = lineas[primera].strip()
        if len(l) <= 80 and (_LINEA_SALUDO.match(l) or _LINEA_PRESENTACION.match(l)):
            lineas = lineas[primera + 1:]
        else:
            break
    # Abajo: una despedida, y el nombre corto que suele ir debajo.
    fin = [i for i, l in enumerate(lineas) if l.strip()]
    if fin:
        ultima = fin[-1]
        penultima = fin[-2] if len(fin) > 1 else None
        es_nombre = re.fullmatch(r"[\wÁÉÍÓÚÑáéíóúñü.\- ]{2,40}", lineas[ultima].strip() or "")
        if _LINEA_FIRMA.match(lineas[ultima].strip()):
            lineas = lineas[:ultima]
        elif (penultima is not None and es_nombre and len(lineas[ultima].split()) <= 4
              and _LINEA_FIRMA.match(lineas[penultima].strip())):
            lineas = lineas[:penultima]
    limpio = _limpiar_lineas("\n".join(lineas))
    # Si todo era saludo y firma, mejor devolver lo que había que dejarlo vacío.
    return limpio or _limpiar_lineas(texto)


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
