"""
Baja a este equipo los archivos de un semestre que están en el sitio (R2).

Cuando el curso se opera desde la página, los CSV nuevos (notas, log,
feedback) quedan en la nube y la copia de `semestres/` en este equipo se queda
atrás. Esto sirve para dos cosas: tener un respaldo propio y saber qué cambió.

**Nunca escribe en `semestres/`.** Baja todo a una carpeta nueva dentro de
`respaldos/web/`, que git ignora porque tiene datos de alumnos. Si se quiere
reemplazar la copia local, se copia a mano desde ahí, sabiendo qué se pisa.

    python -m modulos.web.bajar 2026-2              # respaldo completo
    python -m modulos.web.bajar 2026-2 --comparar   # solo dice qué difiere

Usa WEB_URL y WEB_TOKEN del .env, igual que `subir`.
"""

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from modulos import config
from modulos import semestre as _semestre
from modulos.web.subir import _AGENTE


def _pedir(ruta: str, token: str) -> bytes:
    req = urllib.request.Request(
        f"{config.WEB_URL}/api/motor/{ruta}",
        headers={"Authorization": f"Bearer {token}", "User-Agent": _AGENTE},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def comparar(semestre_id: str, nube: list[dict]) -> dict[str, list[str]]:
    """Qué hay solo en la nube, solo acá, y qué difiere.

    R2 guarda como etag el MD5 del archivo (para archivos subidos de una vez,
    que es como los sube el sitio), así que se compara sin bajar nada.
    """
    raiz = _semestre.raiz(semestre_id)
    locales = {p.relative_to(raiz).as_posix(): p for p in raiz.rglob("*")
               if p.is_file() and "__pycache__" not in p.parts}
    en_nube = {a["ruta"]: a["etag"] for a in nube}
    return {
        "solo en la nube": sorted(set(en_nube) - set(locales)),
        "solo en este equipo": sorted(set(locales) - set(en_nube)),
        "distintos": sorted(r for r in set(en_nube) & set(locales)
                            if en_nube[r].strip('"') != _md5(locales[r])),
    }


def main(semestre_id: str, solo_comparar: bool = False) -> int:
    token = config.cargar_token_web()
    print(f"Sitio: {config.WEB_URL}")
    nube = json.loads(_pedir(f"archivos/{semestre_id}", token))
    if not nube:
        print(f"El sitio no tiene archivos de {semestre_id}.")
        return 1

    for titulo, rutas in comparar(semestre_id, nube).items():
        print(f"\n{titulo}: {len(rutas)}")
        for r in rutas[:30]:
            print(f"  {r}")
        if len(rutas) > 30:
            print(f"  … y {len(rutas) - 30} más")
    if solo_comparar:
        return 0

    destino = config.PROJECT_ROOT / "respaldos" / "web" / datetime.now().strftime("%Y%m%d-%H%M") / semestre_id
    for i, a in enumerate(nube, 1):
        # El sitio ya no deja crear rutas así, pero lo que se escribe en este
        # equipo no depende de eso: nada que salga de la carpeta del respaldo.
        partes = a["ruta"].split("/")
        if a["ruta"].startswith("/") or any(p in ("", ".", "..") or ":" in p or "\\" in p for p in partes):
            print(f"\n  ⊘ se salta una ruta rara: {a['ruta']!r}")
            continue
        ruta = "/".join(urllib.parse.quote(p) for p in partes)
        archivo = destino / a["ruta"]
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_bytes(_pedir(f"archivo/{semestre_id}/{ruta}", token))
        print(f"\r  bajando {i}/{len(nube)}", end="", flush=True)
    print(f"\r✓ {len(nube)} archivos en {destino.relative_to(config.PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if len(args) != 1:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(main(args[0], "--comparar" in sys.argv))
