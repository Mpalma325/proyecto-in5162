"""
Importa el semestre 2025-2 (Primavera 2025) desde la planilla Excel con la que
se llevaba el curso antes de que existiera esta estructura de carpetas.

Genera, en semestres/2025-2/tests_semanales/data/:
  alumnos.csv         50 alumnos, semanas 1..13
  preguntas.csv       las 13 semanas con preguntas y pautas de ambos grupos
  alumnos_extra.csv   aparte: la evaluación "Extra T1" (Discusión Tarea 1), que
                      ocurrió entre la semana 4 y la 5 y no encaja en el
                      esquema numérico del sistema

Es un import de una sola vez, se deja versionado para dejar trazable de dónde
salieron esos datos. No toca el correo ni el semestre activo.

Uso:
    python -m src.importar_2025_2
"""

import csv
import sys

import pandas as pd

from . import config

SEMESTRE = "2025-2"
EXCEL = config.PROJECT_ROOT / "semestres" / "2026-1" / "Preguntas_GPTIN5162_2025-2.xlsx"
DESTINO = config.PROJECT_ROOT / "semestres" / SEMESTRE / "tests_semanales" / "data"

SEMANAS = list(range(1, 14))
COL_GRUPO = "Grupo ( 0 Control; 1 Tratamiento)"


def texto(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "nat") else s


def nota(v) -> str:
    """El sistema guarda las notas con coma decimal."""
    s = texto(v)
    if not s:
        return ""
    try:
        return f"{float(s.replace(',', '.')):.1f}".replace(".", ",")
    except ValueError:
        return s


def col(df, *candidatos):
    """Busca una columna tolerando espacios de más (el Excel los tiene)."""
    normal = {c.replace(" ", "").lower(): c for c in df.columns}
    for cand in candidatos:
        real = normal.get(cand.replace(" ", "").lower())
        if real is not None:
            return real
    return None


def importar_alumnos(al: pd.DataFrame) -> None:
    headers = ["Nombre", "Correo", "Grupo"]
    for s in SEMANAS:
        headers += [f"Envío {s}", f"Nota Test {s}", f"Originalidad {s}", f"Respuesta {s}"]

    filas = []
    for _, r in al.iterrows():
        correo = texto(r.get("Correo")).lower()
        if not correo:
            continue
        grupo = "tratamiento" if texto(r.get(COL_GRUPO)) == "1" else "control"
        fila = {"Nombre": texto(r.get("Nombre")), "Correo": correo, "Grupo": grupo}
        for s in SEMANAS:
            c_env = col(al, f"Envío {s}")
            c_not = col(al, f"Nota Test {s}")
            c_ori = col(al, f"Originalidad {s}")
            fila[f"Envío {s}"] = texto(r.get(c_env)) if c_env else ""
            fila[f"Nota Test {s}"] = nota(r.get(c_not)) if c_not else ""
            fila[f"Originalidad {s}"] = texto(r.get(c_ori)) if c_ori else ""
            fila[f"Respuesta {s}"] = ""  # se llena con reconstruir_interacciones
        filas.append(fila)

    destino = DESTINO / "alumnos.csv"
    with destino.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(filas)
    print(f"  alumnos.csv        {len(filas)} alumnos, semanas 1..13")


def importar_extra(al: pd.DataFrame) -> None:
    """La evaluación 'Extra T1', aparte para no ensuciar el esquema numérico."""
    c_env = col(al, "Envío Extra T1")
    c_not = col(al, "Nota Test Extra T1")
    c_ori = col(al, "Originalidad Extra T1")
    if not c_not:
        print("  (no encontré las columnas de Extra T1, se salta)")
        return

    headers = ["Nombre", "Correo", "Grupo", "Envío", "Nota", "Originalidad"]
    filas = []
    for _, r in al.iterrows():
        correo = texto(r.get("Correo")).lower()
        if not correo:
            continue
        filas.append({
            "Nombre": texto(r.get("Nombre")),
            "Correo": correo,
            "Grupo": "tratamiento" if texto(r.get(COL_GRUPO)) == "1" else "control",
            "Envío": texto(r.get(c_env)) if c_env else "",
            "Nota": nota(r.get(c_not)),
            "Originalidad": texto(r.get(c_ori)) if c_ori else "",
        })

    destino = DESTINO / "alumnos_extra.csv"
    with destino.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(filas)
    con_nota = sum(1 for f in filas if f["Nota"])
    print(f"  alumnos_extra.csv  {len(filas)} alumnos ({con_nota} con nota) — Extra T1")


def importar_preguntas(pr: pd.DataFrame) -> None:
    headers = ["Semana", "Tema", "Fecha de Entrega"]
    for prefijo in ("Control", "Tratamiento"):
        headers += [f"{prefijo} P{i}" for i in (1, 2, 3)]
        headers += [f"{prefijo} Pauta P{i}" for i in (1, 2, 3)]

    filas = []
    for _, r in pr.iterrows():
        semana = texto(r.get("Semana")).strip("'")
        if not semana.isdigit() or int(semana) not in SEMANAS:
            continue  # descarta la 'Extra' y la 14 (vacía)
        fila = {
            "Semana": semana,
            "Tema": texto(r.get("Tema")),
            "Fecha de Entrega": texto(r.get("Fecha de Entrega")),
        }
        for prefijo, origen in (("Control", "Grupo Control"), ("Tratamiento", "Grupo Tratamiento")):
            for i in (1, 2, 3):
                fila[f"{prefijo} P{i}"] = texto(r.get(col(pr, f"{origen}- P{i}")))
                fila[f"{prefijo} Pauta P{i}"] = texto(r.get(col(pr, f"{origen}- Pauta P{i}")))
        filas.append(fila)

    filas.sort(key=lambda f: int(f["Semana"]))
    destino = DESTINO / "preguntas.csv"
    with destino.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(filas)
    print(f"  preguntas.csv      {len(filas)} semanas")


def main() -> None:
    if not EXCEL.exists():
        print(f"No encontré {EXCEL}")
        sys.exit(1)
    DESTINO.mkdir(parents=True, exist_ok=True)

    al = pd.read_excel(EXCEL, sheet_name="Alumnos")
    al.columns = [str(c).strip() for c in al.columns]
    pr = pd.read_excel(EXCEL, sheet_name="Preguntas y Respuestas")
    pr.columns = [str(c).strip() for c in pr.columns]

    print(f"Importando {SEMESTRE} desde {EXCEL.name}")
    importar_alumnos(al)
    importar_extra(al)
    importar_preguntas(pr)
    print(f"\nListo -> {DESTINO.relative_to(config.PROJECT_ROOT)}")
    print("Ahora corre:  python -m src.reconstruir_interacciones 2025-2")


if __name__ == "__main__":
    main()
