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


def extraer_secciones(html_limpio: str) -> dict:
    """
    Corta el HTML limpio en las 4 preguntas + tabla de roles.

    Devuelve dict con keys: 'p1', 'p2', 'p3', 'p4', 'roles_html'
    """
    def cortar(desde: str, hasta_lista: list[str]) -> str:
        i = html_limpio.find(desde)
        if i < 0:
            return ""
        # Buscar el primero de los marcadores de cierre que aparezca
        j_min = -1
        for hasta in hasta_lista:
            j = html_limpio.find(hasta, i + len(desde))
            if j > 0 and (j_min == -1 or j < j_min):
                j_min = j
        return html_limpio[i:j_min] if j_min > 0 else html_limpio[i:]

    secciones = {
        'p1': cortar('pregunta-1', ['pregunta-2']),
        'p2': cortar('pregunta-2', ['pregunta-3']),
        'p3': cortar('pregunta-3', ['pregunta-4']),
        'p4': cortar('pregunta-4', ['id="roles"', "id='roles'", 'id="anexos"', "id='anexos'"]),
    }

    secciones['roles_html'] = _buscar_tabla_roles(html_limpio)

    return secciones


def _buscar_tabla_roles(html_limpio: str) -> str:
    """
    Busca la tabla de roles por su caption.
    El template del curso usa siempre: <strong>Tabla N+1:</strong> Roles de los Participantes...
    """
    # Estrategia 1: encontrar la posición del texto "Roles de los Participantes",
    idx_caption = html_limpio.find('Roles de los Participantes')
    if idx_caption > 0:
        idx_table_open = html_limpio.rfind('<table', 0, idx_caption)
        idx_table_close = html_limpio.find('</table>', idx_caption)
        if idx_table_open >= 0 and idx_table_close > 0:
            return html_limpio[idx_table_open:idx_table_close + len('</table>')]

    # Estrategia 2 (fallback): buscar id="roles"
    m = re.search(r'id\s*=\s*["\']roles["\']', html_limpio)
    if m:
        idx_roles = m.start()
        idx_asim = html_limpio.lower().find('asimismo', idx_roles)
        if idx_asim > 0:
            return html_limpio[idx_roles:idx_asim]
        return html_limpio[idx_roles:idx_roles + 10000]

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


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Uso: python -m src.limpieza_html <archivo.html>")
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
