"""
Qué queda de un correo después de sacarle la cita del mensaje original.

Lo que el modelo evalúa es lo que sale de acá. Si la cita queda pegada, el
modelo ve la pregunta completa como si la hubiera escrito el alumno. Pasó en 30
respuestas de 2026-2 (una de ellas en la semana 7): el correo traía
"El El vie, 25 sep. 2026 … escribió:", con el "El" repetido, una línea en
blanco antes de la cita y fines de línea de Windows.
"""

import sys
import textwrap

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import check, resultado, titulo  # noqa: E402

from modulos.mail.limpieza import _limpiar_respuesta  # noqa: E402

RESPUESTA = ("La densidad condicional se moverá hacia la derecha.\n"
             "El valor esperado condicional aumenta, gracias al dato observado.")
CITA = "Hola Ana,\n\nA continuación encontrarás la pregunta de la semana."


def queda(texto):
    return _limpiar_respuesta(texto).strip()


def citado(texto):
    return "\n".join(f"> {l}" if l else ">" for l in texto.split("\n"))


titulo("1. encabezados de cita que hay que cortar (cita sin marcas '>')")
casos = {
    "Gmail del celular, con 'El' repetido":
        "El El vie, 25 sep. 2026 a la(s) 12:00, <in5162@uchile.cl> escribió:",
    "Gmail en español":
        "El vie, 7 ago 2026 a las 12:15, <in5162@uchile.cl> escribió:",
    "Gmail con 'de' en la fecha":
        "El vie, 11 de sept de 2026, 10:05, <in5162@uchile.cl> escribió:",
    "Gmail en inglés":
        "On Fri, Sep 25, 2026 at 12:00 PM <in5162@uchile.cl> wrote:",
    "Apple Mail":
        "El 25-09-2026, a las 12:00, in5162@uchile.cl escribió:",
    "Outlook":
        "-----Mensaje original-----",
}
for nombre, encabezado in casos.items():
    r = queda(f"{RESPUESTA}\n\n{encabezado}\n\n{CITA}")
    check(nombre, r == RESPUESTA, r[-120:])

titulo("2. cita con marcas '>' (lo más común)")
for nombre, separacion in (("encabezado pegado a la cita", "\n"),
                           ("línea en blanco entre encabezado y cita (el caso de la semana 7)", "\n\n")):
    texto = (f"{RESPUESTA}\n\nEl El vie, 25 sep. 2026 a la(s) 12:00, <in5162@uchile.cl> escribió:"
             f"{separacion}{citado(CITA)}")
    check(nombre, queda(texto) == RESPUESTA, queda(texto)[-120:])
    check(f"{nombre}, con fines de línea de Windows",
          queda(texto.replace("\n", "\r\n")) == RESPUESTA, queda(texto.replace("\n", "\r\n"))[-120:])
dos_lineas = (f"{RESPUESTA}\n\nEl vie, 25 sep 2026 a las 12:00, Equipo IN5162 Coordinación <\n"
              f"in5162@uchile.cl> escribió:\n\n{citado(CITA)}")
check("encabezado partido en dos líneas", queda(dos_lineas) == RESPUESTA, queda(dos_lineas)[-120:])

titulo("3. respuestas escritas dentro de la cita")
intercalada = ("El vie, 25 sep 2026 a las 12:00, <in5162@uchile.cl> escribió:\n\n"
               "> La pregunta 1 es sobre densidades.\n"
               "Mi respuesta a la 1 es que se mueve a la derecha, porque el cliente tuvo el doble "
               "de eventos que la media y el modelo combina lo observado con la población.\n"
               "> La pregunta 2 es sobre la varianza.\n"
               "Mi respuesta a la 2 es que la incertidumbre baja al observar más eventos.")
r = queda(intercalada)
check("se conservan las respuestas del alumno", "Mi respuesta a la 1" in r and "Mi respuesta a la 2" in r, r)

titulo("4. lo que NO hay que cortar")
propio = "El modelo NBD supone llegadas Poisson.\nEl efecto de 16 eventos es mover la media."
check("líneas del alumno que empiezan con 'El'", queda(propio) == propio, queda(propio))
en_medio = "Como dijo el profe:\nEl valor medio es 8, y eso escribió: nada más.\nFin."
check("'escribió:' en medio de una frase", queda(en_medio) == en_medio, queda(en_medio))

titulo("4b. saludo y firma (idea del limpiador de Renzo), sin tocar la respuesta")
casos_saludo = {
    "saludo solo": ("Hola!\n\nEl modelo mejora.", "El modelo mejora."),
    "saludo y presentación": ("Hola! Adjunto mi respuesta c:\n\nEl modelo mejora.", "El modelo mejora."),
    "presentación sola": ("Mis respuestas son las siguientes:\n1. El modelo mejora.", "1. El modelo mejora."),
    "presentación con el nombre de la instancia": ("Mi respuesta al Control 2:\nEl modelo mejora.", "El modelo mejora."),
    "'respuesta al control 2, porque…' es respuesta (se queda)":
        ("Mi respuesta al control 2 es que sí, porque mejora.", "Mi respuesta al control 2 es que sí, porque mejora."),
    "saludo formal": ("Estimado Equipo IN5162,\nEl modelo mejora.", "El modelo mejora."),
    "firma con nombre": ("El modelo mejora.\n\nSaludos cordiales,\nCamila Bravo", "El modelo mejora."),
    "despedida sola": ("El modelo mejora.\nmuchas gracias!", "El modelo mejora."),
    "firma del celular": ("El modelo mejora.\n\nEnviado desde mi iPhone", "El modelo mejora."),
    "saludo con la respuesta en la misma línea (se queda)":
        ("Hola, era necesario para encontrar la diferencia.\nEl modelo mejora.",
         "Hola, era necesario para encontrar la diferencia.\nEl modelo mejora."),
    "respuesta corta que empieza con 'Respuesta:' (se queda)":
        ("Respuesta: sí, porque aumenta la varianza.", "Respuesta: sí, porque aumenta la varianza."),
    "'gracias' dentro de una frase (se queda)":
        ("El modelo mejora gracias a la regularización.", "El modelo mejora gracias a la regularización."),
    "si todo es saludo, no se deja vacío": ("Hola!", "Hola!"),
}
for nombre, (entrada, esperado) in casos_saludo.items():
    check(nombre, queda(entrada) == esperado, queda(entrada))

titulo("5. casos borde que encontró la auditoría")
c = ("Mi respuesta es que sube.\nEl efecto neto es negativo.\n"
     "El 25-09-2026, a las 12:00, in5162@uchile.cl escribió:\nHola Ana, la pregunta.")
check("una línea del alumno que empieza con 'El' justo antes de la cita se conserva",
      queda(c) == "Mi respuesta es que sube.\nEl efecto neto es negativo.", queda(c))
c = "Comentario:\nEl autor lo escribió\n\n> Hola Ana\n> la pregunta"
check("una línea del alumno que termina en 'escribió' (sin dos puntos) se conserva",
      queda(c) == "Comentario:\nEl autor lo escribió", queda(c))
c = ("El vie, 25 sep 2026 a las 12:00, Equipo IN5162 Coordinación <\nin5162@uchile.cl> escribió:\n\n"
     "> P1\nMi respuesta 1, bien larga para que cuente.\n> P2\nMi respuesta 2.")
check("respuesta intercalada con encabezado partido en dos líneas: sale el encabezado",
      queda(c) == "Mi respuesta 1, bien larga para que cuente.\nMi respuesta 2.", queda(c))

titulo("6. un correo que trae solo la cita (prueba de Tareas del 19/11/2026)")
from modulos.mail.limpieza import es_solo_eco  # noqa: E402

PLANTILLA = ("Hola {nombre},\n\nTe escribimos desde el curso ZZ9999 por la revisión de la {tarea}, con una "
             "pregunta breve sobre el código que declaraste.\n\nPregunta (sobre la {pregunta_tarea} de tu grupo):"
             "\n\n{pregunta}\n\nResponde directamente a este correo.\n\nPlazo de respuesta: {plazo} hrs. Tienes "
             "{minutos} minutos para responder a este correo.\n\nSaludos,\nEquipo ZZ9999")
PREGUNTA = "¿Por qué filtraste PROM_GRAL >= 10 antes de construir base_limpia?"
VALORES = {"nombre": None, "tarea": "T1", "pregunta_tarea": "P2", "pregunta": PREGUNTA,
           "plazo": "hoy jueves 19 de noviembre de 2026, hasta las 17:55"}
enviado = PLANTILLA.format(nombre="Ana", tarea="T1", pregunta_tarea="P2", pregunta=PREGUNTA,
                           plazo=VALORES["plazo"], minutos=25)
ENCABEZADO = "El jue, 19 nov 2026 a las 17:20, Curso <curso@x.cl> escribió:"
vacio = queda(f"\n{ENCABEZADO}\n{citado(enviado)}\n")
check("(así queda hoy: la pregunta como si la hubiera escrito el alumno)", PREGUNTA in vacio, vacio[:120])
check("solo la cita es eco del correo enviado", es_solo_eco(vacio, PLANTILLA, VALORES), vacio)
# Hay clientes que cortan las líneas largas al citar, entre palabras.
cortado = "\n".join(l for linea in enviado.splitlines() for l in (textwrap.wrap(linea, 60) or [""]))
check("también con las líneas cortadas al citar",
      es_solo_eco(queda(f"\n{ENCABEZADO}\n{citado(cortado)}\n"), PLANTILLA, VALORES))
check("también sin conocer el plazo (los campos que faltan calzan con cualquier texto)",
      es_solo_eco(vacio, PLANTILLA, {**VALORES, "plazo": None}))
adentro = enviado.replace(PREGUNTA, PREGUNTA + "\nFiltré porque bajo 10 las notas venían en otra escala.")
r = queda(f"\n{ENCABEZADO}\n{citado(adentro)}\n")
check("con una línea propia escrita dentro de la cita, no es eco (y la línea se conserva)",
      not es_solo_eco(r, PLANTILLA, VALORES) and "otra escala" in r, r)
check("una respuesta normal no es eco",
      not es_solo_eco("Filtré porque bajo 10 las notas venían en otra escala.", PLANTILLA, VALORES))
check("una respuesta corta que repite palabras de la pregunta no es eco",
      not es_solo_eco("Por base_limpia.", PLANTILLA, VALORES))
check("un texto vacío no es eco (ya cuenta como vacío por otro lado)", not es_solo_eco("", PLANTILLA, VALORES))

sys.exit(resultado())
