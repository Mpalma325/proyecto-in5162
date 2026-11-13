"""
Limpieza de HTMLs renderizados de RMarkdown.

Uso:
    from limpieza_html import limpiar_html, extraer_secciones, extraer_tabla_roles, extraer_codigo_r_de_clase
"""

import re
import html as htmlmod
from pathlib import Path


def limpiar_html(html: str) -> str:
    """Aplica toda la cadena de limpieza a un HTML de entrega."""
    html = re.sub(r'<img[^>]*base64[^>]*>', '', html)
    html = re.sub(r'<pre><code>[\s\S]*?</code></pre>', '', html)
    html = re.sub(r'<p><strong>[^<]*</strong></p>', '', html)
    html = re.sub(r'<span[^>]*>', '', html)
    html = re.sub(r'</span>', '', html)
    html = re.sub(r'<a[^>]*>', '', html)
    html = re.sub(r'</a>', '', html)
    # Decodificar entidades HTML
    html = htmlmod.unescape(html)
    return html


# Los ids de sección que genera el template del curso son `pregunta-1`..`pregunta-4`,
# pero varios grupos renombran el encabezado y RMarkdown deriva otro id. Estos son
# los que aparecieron en la entrega de T1; el orden es de más específico a menos.
_IDS_PREGUNTA = {
    1: ("pregunta-1", "desarrollo-p1", "p1"),
    2: ("pregunta-2", "desarrollo-p2", "p2"),
    3: ("pregunta-3", "desarrollo-p3", "p3"),
    4: ("pregunta-4", "desarrollo-p4", "p4"),
}
_RE_PREGUNTA_SUELTA = {n: re.compile(r"#{2,6}\s*(?:\*\*)?\s*Pregunta\s*" + str(n) + r"\b", re.I)
                       for n in (1, 2, 3, 4)}
# Dónde termina la última pregunta.
_IDS_CIERRE = ("roles", "resumen", "anexos")
# Dónde empieza el desarrollo, para cuando el grupo no marcó la pregunta 1 y
# escribió sus propios subtítulos.
_IDS_APERTURA = ("desarrollo", "preliminares")


def _pos_id(html: str, ids: tuple[str, ...]) -> int:
    """Posición del primer `id="X"` presente, probando los ids en orden."""
    for id_ in ids:
        m = re.search(r"""id\s*=\s*["']""" + re.escape(id_) + r"""["']""", html)
        if m:
            return m.start()
    return -1


def extraer_secciones(html_limpio: str) -> dict:
    """
    Corta el HTML limpio en las 4 preguntas + tabla de roles.

    Devuelve dict con keys: 'p1', 'p2', 'p3', 'p4', 'roles_html'
    """
    inicios = {n: _pos_id(html_limpio, ids) for n, ids in _IDS_PREGUNTA.items()}
    # Un encabezado sin línea en blanco antes no se renderiza: queda como texto
    # "### Pregunta 2" al final del párrafo anterior (pasó en T2 de 2026-2).
    for n in (1, 2, 3, 4):
        if inicios[n] < 0:
            m = _RE_PREGUNTA_SUELTA[n].search(html_limpio, max(inicios[n - 1], 0) if n > 1 else 0)
            if m:
                inicios[n] = m.start()
    cierre = _pos_id(html_limpio, _IDS_CIERRE)
    if cierre < 0:
        cierre = len(html_limpio)

    # Sin ancla para la pregunta 1, su contenido es todo lo que va entre el
    # inicio del desarrollo y la primera pregunta que sí quedó marcada.
    if inicios[1] < 0:
        inicios[1] = _pos_id(html_limpio, _IDS_APERTURA)

    secciones = {}
    for n in (1, 2, 3, 4):
        i = inicios[n]
        if i < 0:
            secciones[f"p{n}"] = ""
            continue
        # El corte va hasta la siguiente pregunta que exista, o hasta el cierre.
        posteriores = [inicios[m] for m in range(n + 1, 5) if inicios[m] > i]
        posteriores.append(cierre if cierre > i else len(html_limpio))
        secciones[f"p{n}"] = html_limpio[i:min(posteriores)]

    secciones['roles_html'] = _buscar_tabla_roles(html_limpio)

    return secciones


# Palabras con que el template pide llenar las celdas de rol.
_ROLES_ESPERADOS = ("codigo", "código", "interpretacion", "interpretación", "ambos", "uso")


def _parece_tabla_de_roles(tabla_html: str) -> bool:
    """
    ¿Esta tabla es la de roles y no otra del documento?

    Se acepta por el encabezado de la primera columna o por el contenido de las
    celdas. Hace falta porque el caption también aparece dentro del bloque de
    código cuando el grupo entrega con echo=TRUE, y ahí el `<table>` anterior es
    cualquier tabla de resultados.
    """
    filas = extraer_tabla_roles(tabla_html)
    if not filas:
        return False
    columnas = list(filas[0].keys())
    if columnas and any(k in columnas[0].lower()
                        for k in ("integrante", "nombre", "participante", "alumno")):
        return True
    celdas = " ".join(v for f in filas for v in list(f.values())[1:]).lower()
    return any(r in celdas for r in _ROLES_ESPERADOS)


def _buscar_tabla_roles(html_limpio: str) -> str:
    """
    Busca la tabla de roles por su caption.
    El template del curso usa siempre: <strong>Tabla N+1:</strong> Roles de los Participantes...
    """
    candidatos = []

    # Estrategia 1: las ocurrencias del texto "Roles de los Participantes"
    # (insensible a mayúsculas: algunos alumnos escriben "participantes" en
    # minúscula). Se recorren de la última a la primera porque la primera puede
    # ser el `caption =` del bloque de código, cuya tabla real viene después.
    low = html_limpio.lower()
    idx_caption = low.rfind('roles de los participantes')
    while idx_caption > 0:
        idx_table_open = html_limpio.rfind('<table', 0, idx_caption)
        idx_table_close = html_limpio.find('</table>', idx_caption)
        if idx_table_open >= 0 and idx_table_close > 0:
            candidatos.append(html_limpio[idx_table_open:idx_table_close + len('</table>')])
        idx_caption = low.rfind('roles de los participantes', 0, idx_caption)

    # Estrategia 2 (fallback): buscar id="roles"
    m = re.search(r"""id\s*=\s*["']roles["']""", html_limpio)
    if m:
        idx_roles = m.start()
        idx_asim = low.find('asimismo', idx_roles)
        if idx_asim > 0:
            candidatos.append(html_limpio[idx_roles:idx_asim])
        else:
            candidatos.append(html_limpio[idx_roles:idx_roles + 10000])

    for candidato in candidatos:
        if _parece_tabla_de_roles(candidato):
            return candidato

    return ""


def extraer_tabla_roles(roles_html: str) -> list[dict]:
    """
    Parsea la tabla HTML de roles a una lista de dicts.

    """
    m = re.search(r'<table[^>]*>(.*?)</table>', roles_html, re.DOTALL)
    if not m:
        return []
    tabla = m.group(1)

    thead = re.search(r'<thead[^>]*>(.*?)</thead>', tabla, re.DOTALL)
    if thead:
        headers = re.findall(r'<th[^>]*>(.*?)</th>', thead.group(1), re.DOTALL)
    else:
        primera_tr = re.search(r'<tr[^>]*>(.*?)</tr>', tabla, re.DOTALL)
        if not primera_tr:
            return []
        headers = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', primera_tr.group(1), re.DOTALL)
    headers = [_limpiar_celda(h) for h in headers]

    tbody = re.search(r'<tbody[^>]*>(.*?)</tbody>', tabla, re.DOTALL)
    if tbody:
        filas_raw = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody.group(1), re.DOTALL)
    else:
        todas = re.findall(r'<tr[^>]*>(.*?)</tr>', tabla, re.DOTALL)
        filas_raw = todas[1:] if len(todas) > 1 else []

    resultado = []
    for fila in filas_raw:
        celdas = re.findall(r'<td[^>]*>(.*?)</td>', fila, re.DOTALL)
        celdas = [_limpiar_celda(c) for c in celdas]
        if not celdas:
            continue
        if len(celdas) < len(headers):
            celdas = celdas + [""] * (len(headers) - len(celdas))
        resultado.append(dict(zip(headers, celdas)))

    return resultado


def _limpiar_celda(celda: str) -> str:
    """Limpia el contenido de una celda <td> o <th>."""
    celda = re.sub(r'<[^>]+>', '', celda)
    celda = re.sub(r'\s+', ' ', celda).strip()
    if celda in ('', '•', '·', '\xa0', '*'):
        return ""
    return celda


def extraer_codigo_r_de_clase(path: str | Path) -> str:
    """
    Extrae solo los bloques de código R de un HTML renderizado de clase.
    """
    html = Path(path).read_text(encoding='utf-8')
    bloques = re.findall(
        r'<pre class="sourceCode r"><code class="sourceCode r">(.*?)</code></pre>',
        html, re.DOTALL
    )
    codigo = []
    for b in bloques:
        b = re.sub(r'<span[^>]*>', '', b)
        b = re.sub(r'</span>', '', b)
        b = re.sub(r'<a[^>]*>.*?</a>', '', b, flags=re.DOTALL)
        b = htmlmod.unescape(b)
        codigo.append(b.strip())
    return '\n\n# ---\n\n'.join(codigo)


# Nombres con que viene la tabla del template, que algunos grupos no reemplazan.
_NOMBRES_PLACEHOLDER = ("null", "na", "n/a", "-")

# Bajo esto, sumando las cuatro secciones, la entrega es el template sin
# desarrollar: en T1 la más corta de las entregas reales pasó los 39.000.
_MINIMO_CONTENIDO = 8000


def es_nombre_placeholder(nombre: str) -> bool:
    """¿Es 'Integrante 2', 'Null' o similar en vez del nombre de una persona?"""
    n = nombre.strip().lower()
    return (not n
            or n in _NOMBRES_PLACEHOLDER
            or bool(re.fullmatch(r'(integrante|alumno|nombre|autor)\s*\d*', n)))


def revisar_entrega(secciones: dict) -> list[str]:
    """
    Motivos por los que no vale la pena mandar esta entrega al modelo.

    Lista vacía significa que se puede procesar. Se corre antes de llamar a la
    API porque una entrega en blanco igual gasta tokens y devuelve preguntas
    inventadas sobre código que nadie escribió.
    """
    motivos = []

    total = sum(len(secciones.get(f"p{n}", "")) for n in (1, 2, 3, 4))
    vacias = [n for n in (1, 2, 3, 4) if not secciones.get(f"p{n}")]
    if len(vacias) == 4:
        motivos.append("no se pudo recortar ninguna de las cuatro preguntas")
    elif total < _MINIMO_CONTENIDO:
        motivos.append(f"entrega casi vacía ({total} caracteres en las cuatro preguntas)")

    filas = extraer_tabla_roles(secciones.get("roles_html", ""))
    if not filas:
        motivos.append("no se encontró la tabla de roles")
    elif all(es_nombre_placeholder(list(f.values())[0]) for f in filas):
        motivos.append("la tabla de roles quedó con los nombres del template")

    return motivos

def extraer_autores(html: str) -> list[str]:
    """
    Los integrantes según el encabezado del documento.

    RMarkdown deja el campo `author` del YAML en un <meta> del head, que
    sobrevive aunque el grupo no haya llenado la tabla de roles. No dice quién
    hizo qué, solo quiénes son.
    """
    m = re.search(r'<meta\s+name="author"\s+content="([^"]*)"', html)
    if not m:
        # Algunas plantillas de RMarkdown no dejan el <meta>, pero sí el
        # encabezado visible (T2 de 2026-2).
        m = re.search(r'<h4\s+class="author">\s*([^<]+?)\s*</h4>', html)
    if not m:
        # El .Rmd todavía no está renderizado: el campo sigue en el YAML.
        m = re.search(r'^author:\s*"?([^"\n]+?)"?\s*$', html, re.M)
    if not m:
        return []
    crudo = htmlmod.unescape(m.group(1))
    partes = re.split(r'\s*,\s*|\s+y\s+|\s*;\s*', crudo)
    autores = []
    for parte in partes:
        nombre = parte.strip().strip('.').strip()
        if nombre:
            autores.append(nombre)
    return autores


# Encabezados con que el template marca cada pregunta en el .Rmd.
_RE_PREGUNTA_RMD = re.compile(r'^#{1,6}\s*\**\s*Pregunta\s*([1-4])\b', re.M | re.I)
_RE_CIERRE_RMD = re.compile(r'^#{1,6}\s*\**\s*(Roles|Resumen|Anexos)\b', re.M | re.I)


def secciones_desde_rmd(texto: str) -> dict:
    """
    Las mismas cuatro secciones, pero cortadas del .Rmd en vez del HTML.

    Sirve cuando el grupo entrega un HTML renderizado antes de escribir el
    código: el HTML queda con los comentarios del template y el .Rmd al lado
    tiene el trabajo. El corte es por encabezado markdown; no hay tabla de roles
    porque en el .Rmd es código que todavía no se ejecutó.
    """
    marcas = [(int(m.group(1)), m.start()) for m in _RE_PREGUNTA_RMD.finditer(texto)]
    cierre = _RE_CIERRE_RMD.search(texto, marcas[-1][1] if marcas else 0)
    fin_doc = cierre.start() if cierre else len(texto)

    secciones = {f"p{n}": "" for n in (1, 2, 3, 4)}
    for i, (n, inicio) in enumerate(marcas):
        fin = marcas[i + 1][1] if i + 1 < len(marcas) else fin_doc
        secciones[f"p{n}"] = texto[inicio:fin]

    secciones["roles_html"] = ""
    return secciones

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Uso: python -m modulos.tareas.limpieza_html <archivo.html>")
        sys.exit(1)
    html = Path(sys.argv[1]).read_text(encoding='utf-8')
    limpio = limpiar_html(html)
    secciones = extraer_secciones(limpio)
    for k in ('p1', 'p2', 'p3', 'p4'):
        print(f"\n=== {k.upper()} ({len(secciones[k])} chars) ===")
        print(secciones[k][:300] if secciones[k] else "(vacío)")
    print(f"\n=== TABLA DE ROLES (HTML, {len(secciones['roles_html'])} chars) ===")
    for fila in extraer_tabla_roles(secciones['roles_html']):
        print(fila)
