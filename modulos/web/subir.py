"""
Sube el panel de cada semestre al sitio web del curso.

El sitio muestra la reportería a quien tenga acceso, desde cualquier equipo o
teléfono. Los datos siguen viviendo acá, en semestres/<id>/; lo que se sube es
el resultado de `datos.reportes.panel()`, la misma tabla que dibuja Streamlit.

**Solo lee.** No manda correos, no llama al modelo y no modifica ningún CSV.

    python -m modulos.web.subir               # el panel de todos los semestres
    python -m modulos.web.subir 2026-2        # uno
    python -m modulos.web.subir --archivos    # además, las carpetas completas a R2
    python -m modulos.web.subir --simular     # dice qué subiría, sin conectarse

Con --archivos se copian a R2 todos los archivos de cada semestre, con las
mismas rutas que tienen acá, y la plantilla de semestres nuevos. Es lo que usa el motor en la nube como disco, y se
hace una vez para migrar; después el motor los mantiene al día.

Necesita en el .env: WEB_URL (por defecto el sitio local de desarrollo) y
WEB_TOKEN, el mismo valor que tiene el Worker como secreto TOKEN_MOTOR.
"""

import json
import sys
import urllib.error
import urllib.request

from modulos import config
from modulos import semestre as _semestre
from modulos.datos import TESTS, reportes

# Cloudflare rechaza con 403 (error 1010) el agente por defecto de urllib.
_AGENTE = "in5162-subir/1.0"


def _subir(semestre_id: str, filas: list[dict], activo: bool, token: str) -> dict:
    cuerpo = json.dumps({"activo": activo, "filas": filas}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{config.WEB_URL}/api/subir/{semestre_id}",
        data=cuerpo, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": f"Bearer {token}", "User-Agent": _AGENTE},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def _subir_archivo(semestre_id: str, ruta: str, datos: bytes, token: str) -> None:
    from urllib.parse import quote

    destino = "/".join(quote(p) for p in ruta.split("/"))
    req = urllib.request.Request(
        f"{config.WEB_URL}/api/motor/archivo/{semestre_id}/{destino}",
        data=datos, method="PUT",
        headers={"Content-Type": "application/octet-stream", "Authorization": f"Bearer {token}",
                 "User-Agent": _AGENTE, "X-In5162-Origen": "subida desde el PC"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        r.read()


def _en_la_nube(semestre_id: str, token: str) -> dict[str, str]:
    """{ruta: etag} de lo que el sitio ya tiene. El etag de R2 es el MD5 del archivo."""
    req = urllib.request.Request(
        f"{config.WEB_URL}/api/motor/archivos/{semestre_id}",
        headers={"Authorization": f"Bearer {token}", "User-Agent": _AGENTE},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return {a["ruta"]: a["etag"].strip('"') for a in json.loads(r.read())}


def _subir_carpeta(semestre_id: str, token: str) -> tuple[int, int, list[str]]:
    """Sube lo que falta o cambió. Devuelve (subidos, iguales, fallidos).

    Lo idéntico no se vuelve a subir: cada subida deja una versión en el
    historial del sitio, y resubir todo lo llenaría de copias iguales. Un
    archivo que falla no detiene al resto: se informa al final.
    """
    import hashlib

    raiz = _semestre.raiz(semestre_id)
    nube = _en_la_nube(semestre_id, token)
    subidos, iguales, fallidos = 0, 0, []
    lista = _archivos_de(semestre_id)
    for i, p in enumerate(lista, 1):
        ruta = p.relative_to(raiz).as_posix()
        datos = p.read_bytes()
        if nube.get(ruta) == hashlib.md5(datos).hexdigest():
            iguales += 1
        else:
            try:
                _subir_archivo(semestre_id, ruta, datos, token)
                subidos += 1
            except urllib.error.HTTPError as e:
                fallidos.append(f"{ruta} ({e.code}: {e.read().decode('utf-8', 'replace')[:120]})")
        print(f"\r  {semestre_id}: {i}/{len(lista)} archivos", end="", flush=True)
    print()
    return subidos, iguales, fallidos


def _archivos_de(semestre_id: str) -> list:
    raiz = _semestre.raiz(semestre_id)
    return sorted(p for p in raiz.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts
                  and not p.name.endswith((".tmp", ".pyc")))


def main(filtro: str | None = None, simular: bool = False, archivos: bool = False) -> int:
    activo = _semestre.activo()
    semestres = [s for s in _semestre.listar() if not s.startswith("_")]
    if filtro:
        semestres = [s for s in semestres if s == filtro]
        if not semestres:
            print(f"No existe el semestre {filtro}.")
            return 1

    print(f"Sitio: {config.WEB_URL}")
    token = None if simular else config.cargar_token_web()

    fallidos = 0
    if archivos and not filtro:
        # La plantilla también: el sitio crea los semestres nuevos copiándola,
        # igual que semestre.crear() en el PC. No tiene datos de alumnos.
        lista = _archivos_de("_template")
        if simular:
            print(f"  _template: subiría {len(lista)} archivos a R2")
        else:
            subidos, iguales, malos = _subir_carpeta("_template", token)
            fallidos += len(malos)
            print(f"  {'✗' if malos else '✓'} _template: {subidos} subidos, {iguales} ya estaban")
            for m in malos:
                print(f"     ✗ {m}")
    for sid in semestres:
        filas = reportes.panel(sid, TESTS)
        marca = "  (activo)" if sid == activo else ""
        if archivos:
            lista = _archivos_de(sid)
            total = sum(p.stat().st_size for p in lista)
            if simular:
                print(f"  {sid}: subiría {len(lista)} archivos a R2 ({total / 1048576:.1f} MB)")
            else:
                subidos, iguales, malos = _subir_carpeta(sid, token)
                fallidos += len(malos)
                print(f"  {'✗' if malos else '✓'} {sid}: {subidos} subidos, {iguales} ya estaban "
                      f"({total / 1048576:.1f} MB en total)")
                for m in malos:
                    print(f"     ✗ {m}")
        if simular:
            print(f"  {sid}: subiría {len(filas)} filas{marca}")
            continue
        try:
            r = _subir(sid, filas, sid == activo, token)
            print(f"  ✓ {sid}: {r['filas']} filas{marca}")
        except urllib.error.HTTPError as e:
            fallidos += 1
            detalle = e.read().decode("utf-8", "replace")[:200]
            print(f"  ✗ {sid}: el sitio respondió {e.code}: {detalle}")
        except urllib.error.URLError as e:
            fallidos += 1
            print(f"  ✗ {sid}: no pude conectarme a {config.WEB_URL} ({e.reason})")
            if "127.0.0.1" in config.WEB_URL or "localhost" in config.WEB_URL:
                print("    ¿Está corriendo el sitio local? En web/: npm run dev")
            break
    return 1 if fallidos else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    sim = "--simular" in args
    resto = [a for a in args if not a.startswith("-")]
    raise SystemExit(main(resto[0] if resto else None, sim, "--archivos" in args))
