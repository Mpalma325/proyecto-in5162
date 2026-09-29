"""Exporta las notas y los pendientes de una tarea, sin correo ni API."""

import argparse
import csv
from pathlib import Path

from modulos import datos
from . import config, storage


def filas_reporte(tarea: str) -> list[dict]:
    notas = {n['Correo'].strip().lower(): n
             for n in datos.notas.leer(flujo=datos.TAREAS, item=tarea)}
    alumnos = datos.alumnos.por_correo()
    resultado, vistos = [], set()
    for f in storage.leer_csv(tarea):
        correo = f.get('alumno_correo', '').strip().lower()
        if correo and correo in vistos:
            raise ValueError(f'Correo duplicado en {tarea}: {correo}')
        vistos.add(correo)
        n = notas.get(correo, {})
        enviada = bool(n.get('Enviado', '').strip())
        respondio = bool(n.get('Respondio', '').strip())
        nota = n.get('Nota', '').strip()
        ajuste = ''
        accion = 'Pendiente'
        if nota:
            valor = float(nota.replace(',', '.'))
            ajuste = (f'{valor:+.1f}' if valor else '0.0').replace('.', ',')
            accion = 'Sumar' if valor > 0 else 'Restar' if valor < 0 else 'Sin ajuste'
        estado = ('Respondió' if respondio else 'Sin respuesta' if enviada
                  else 'Sin envío')
        resultado.append({
            'Alumno': alumnos.get(correo, {}).get('Nombre') or f['alumno_nombre'],
            'Correo': correo, 'Grupo': Path(f['grupo_archivo']).stem,
            'Pregunta': f.get('pregunta_tarea', ''),
            'Enviado': 'sí' if enviada else 'no',
            'Respondió': 'sí' if respondio else 'no',
            'Ajuste en nota': ajuste, 'Acción': accion, 'Estado': estado,
        })
    return sorted(resultado, key=lambda f: f['Alumno'].casefold())


def exportar(tarea: str) -> tuple[Path, Path]:
    filas = filas_reporte(tarea)
    if not filas:
        raise ValueError(f'No hay alumnos registrados para {tarea}.')
    config.SALIDAS.mkdir(parents=True, exist_ok=True)
    notas = config.SALIDAS / f'notas_{tarea}_para_equipo.csv'
    pendientes = config.SALIDAS / f'sin_respuesta_{tarea}.csv'
    sin_respuesta = [f for f in filas if f['Estado'] == 'Sin respuesta']
    for destino, contenido in ((notas, filas), (pendientes, sin_respuesta)):
        with destino.open('w', encoding='utf-8-sig', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=list(filas[0]))
            writer.writeheader()
            writer.writerows(contenido)
    print(f'{tarea}: {len(filas)} alumnos; '
          f'{sum(f["Respondió"] == "sí" for f in filas)} respondieron; '
          f'{len(sin_respuesta)} sin respuesta.')
    print(notas)
    print(pendientes)
    return notas, pendientes


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tarea', type=str.upper)
    args = parser.parse_args()
    exportar(args.tarea)
