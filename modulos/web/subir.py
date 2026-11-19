"""
Sube semestres de este equipo al sitio web del curso (la migración a la nube).

Desde que el curso se opera en el sitio, **la nube es la fuente**: el motor
mantiene al día los archivos y la reportería. Por eso esto solo agrega lo que
allá no existe: un semestre nuevo, un archivo nuevo. Lo que ya está en la nube
y es distinto acá no se toca (la copia de acá suele ser la vieja), salvo que se
pida con --forzar; en ese caso la versión reemplazada queda en el historial.

    python -m modulos.web.subir 2026-2 --archivos     # agrega lo que falta de 2026-2
    python -m modulos.web.subir --archivos            # todos los semestres y la plantilla
    python -m modulos.web.subir 2026-2 --simular      # dice qué haría, sin tocar nada
    python -m modulos.web.subir 2026-2 --archivos --forzar   # reemplaza también lo distinto

Sin --archivos solo se sube la reportería, y solo de semestres que la nube
todavía no tiene. **No manda correos, no llama al modelo y no modifica ningún
archivo de este equipo.** Para traer lo de la nube acá: `modulos.web.bajar`.

Necesita en el .env: WEB_URL y WEB_TOKEN (el mismo valor que el secreto
TOKEN_MOTOR del Worker).
"""

import hashlib
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import quote

from modulos import config
from modulos import semestre as _semestre
from modulos.datos import TESTS, reportes

# Cloudflare rechaza con 403 (error 1010) el agente por defecto de urllib.
_AGENTE = "in5162-subir/1.0"


def _pedir(metodo: str, ruta: str, token: str, cuerpo: bytes | None = None,
           extra: dict | None = None, tipo: str = "application/octet-stream") -> bytes:
    req = urllib.request.Request(
        f"{config.WEB_URL}/api/{ruta}", data=cuerpo, method=metodo,
        headers={"Content-Type": tipo, "Authorization": f"Bearer {token}",
                 "User-Agent": _AGENTE, **(extra or {})},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def _sin_nan(v):
    # Una nota "nan" llega como float('nan') y json.dumps la escribe como NaN,
    # que no es JSON válido: el sitio rechazaba el panel entero.
    return None if isinstance(v, float) and v != v else v


def _subir_panel(semestre_id: str, filas: list[dict], activo: bool | None, token: str) -> dict:
    cuerpo = {"filas": [{k: _sin_nan(v) for k, v in f.items()} for f in filas]}
    if activo is not None:
        cuerpo["activo"] = activo
    return json.loads(_pedir("POST", f"subir/{semestre_id}", token,
                             json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
                             tipo="application/json; charset=utf-8"))


def _subir_archivo(semestre_id: str, ruta: str, datos: bytes, token: str, etag: str | None) -> None:
    """Con etag, reemplaza solo esa versión; sin etag, solo si el archivo no existe."""
    destino = "/".join(quote(p) for p in ruta.split("/"))
    condicion = {"If-Match": etag} if etag else {"If-None-Match": "*"}
    _pedir("PUT", f"motor/archivo/{semestre_id}/{destino}", token, datos,
           extra={"X-In5162-Origen": "subida desde el PC", **condicion})


def _en_la_nube(semestre_id: str, token: str) -> dict[str, str]:
    """{ruta: etag} de lo que el sitio ya tiene. El etag de R2 es el MD5 del archivo."""
    return {a["ruta"]: a["etag"].strip('"')
            for a in json.loads(_pedir("GET", f"motor/archivos/{semestre_id}", token))}


def _archivos_de(semestre_id: str) -> list:
    raiz = _semestre.raiz(semestre_id)
    return sorted(p for p in raiz.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts
                  and not p.name.endswith((".tmp", ".pyc")))


def _contenido(semestre_id: str, p, valores: dict[str, str] | None) -> bytes:
    """Los bytes que se suben. La plantilla del repositorio tiene marcas
    («CURSO», «PROFESOR»...) donde va el nombre del curso: sube llena, igual que
    la sube instalar.py, porque el sitio crea los semestres copiándola tal cual.
    Un archivo sin marcas sube tal cual: así su MD5 sigue calzando con el de R2."""
    datos = p.read_bytes()
    if valores is None or p.suffix.lower() not in (".md", ".csv", ".txt", ".json"):
        return datos
    texto = datos.decode("utf-8")
    lleno = _semestre.llenar_marcas(texto, valores)
    if lleno == texto:
        return datos
    return lleno.replace("\r\n", "\n").encode("utf-8")


def _subir_carpeta(semestre_id: str, token: str | None, nube: dict[str, str],
                   forzar: bool, simular: bool,
                   valores: dict[str, str] | None = None) -> dict[str, list[str]]:
    """Clasifica cada archivo de acá y sube lo que corresponde.

    Con `valores`, llena las marcas de la plantilla antes de comparar y subir.
    Devuelve {"nuevos", "iguales", "distintos", "reemplazados", "fallidos"}.
    """
    raiz = _semestre.raiz(semestre_id)
    r = {k: [] for k in ("nuevos", "iguales", "distintos", "reemplazados", "fallidos")}
    lista = _archivos_de(semestre_id)
    for i, p in enumerate(lista, 1):
        ruta = p.relative_to(raiz).as_posix()
        datos = _contenido(semestre_id, p, valores)
        etag = nube.get(ruta)
        if etag == hashlib.md5(datos).hexdigest():
            r["iguales"].append(ruta)
            continue
        if etag and not forzar:
            r["distintos"].append(ruta)
            continue
        if not simular:
            try:
                _subir_archivo(semestre_id, ruta, datos, token, etag)
            except urllib.error.HTTPError as e:
                r["fallidos"].append(f"{ruta} ({e.code}: {e.read().decode('utf-8', 'replace')[:120]})")
                continue
        r["reemplazados" if etag else "nuevos"].append(ruta)
        print(f"\r  {semestre_id}: {i}/{len(lista)} archivos", end="", flush=True)
    print(f"\r{' ' * 40}\r", end="")
    return r


def _informar(sid: str, r: dict[str, list[str]], simular: bool) -> None:
    verbo = "subiría" if simular else "subidos"
    malos = r["fallidos"]
    print(f"  {'✗' if malos else '✓'} {sid}: {len(r['nuevos'])} nuevos {verbo}, "
          f"{len(r['iguales'])} iguales"
          + (f", {len(r['reemplazados'])} reemplazados" if r["reemplazados"] else ""))
    if r["distintos"]:
        print(f"    ⊘ {len(r['distintos'])} distintos en la nube, no se tocaron "
              f"(la nube es la fuente; --forzar para reemplazarlos):")
        for ruta in r["distintos"][:15]:
            print(f"       {ruta}")
    for m in malos:
        print(f"    ✗ {m}")


def main(filtro: str | None = None, simular: bool = False, archivos: bool = False,
         forzar: bool = False) -> int:
    activo = _semestre.activo()
    semestres = [s for s in _semestre.listar() if not s.startswith("_")]
    if filtro:
        semestres = [s for s in semestres if s == filtro]
        if not semestres:
            print(f"No existe el semestre {filtro}.")
            return 1

    print(f"Sitio: {config.WEB_URL}" + ("   (simulación: no se sube nada)" if simular else ""))
    token = config.cargar_token_web()
    fallidos = 0
    try:
        if archivos and not filtro:
            # La plantilla también: el sitio crea los semestres nuevos copiándola.
            try:
                r = _subir_carpeta("_template", token, _en_la_nube("_template", token), forzar,
                                   simular, _semestre.datos_del_curso())
                _informar("_template", r, simular)
                fallidos += len(r["fallidos"])
            except ValueError as e:
                print(f"  ✗ _template no se subió: {e}")
                fallidos += 1
        for sid in semestres:
            nube = _en_la_nube(sid, token)
            nuevo_en_la_nube = not nube
            if archivos:
                r = _subir_carpeta(sid, token, nube, forzar, simular)
                _informar(sid, r, simular)
                fallidos += len(r["fallidos"])
            # La reportería de un semestre que ya vive en la nube la mantiene el
            # motor: la de acá está calculada con datos que pueden ser viejos.
            if not (nuevo_en_la_nube or forzar):
                print(f"  ⊘ {sid}: la reportería de la nube no se toca (la mantiene el motor)")
                continue
            filas = reportes.panel(sid, TESTS)
            if simular:
                print(f"  {sid}: subiría la reportería ({len(filas)} filas)")
                continue
            # El semestre activo solo se marca al llegar por primera vez; después se
            # elige en la página, y el activo de este equipo no lo pisa.
            marca_activo = (sid == activo) if nuevo_en_la_nube else None
            respuesta = _subir_panel(sid, filas, marca_activo, token)
            print(f"  ✓ {sid}: reportería con {respuesta['filas']} filas"
                  + ("  (activo)" if marca_activo else ""))
    except urllib.error.HTTPError as e:
        print(f"  ✗ el sitio respondió {e.code}: {e.read().decode('utf-8', 'replace')[:200]}")
        return 1
    except urllib.error.URLError as e:
        print(f"  ✗ no pude conectarme a {config.WEB_URL} ({e.reason})")
        if "127.0.0.1" in config.WEB_URL or "localhost" in config.WEB_URL:
            print("    ¿Está corriendo el sitio local? En web/: npm run dev")
        return 1
    return 1 if fallidos else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    resto = [a for a in args if not a.startswith("-")]
    raise SystemExit(main(resto[0] if resto else None, "--simular" in args,
                          "--archivos" in args, "--forzar" in args))
