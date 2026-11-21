# Módulo `semestre`

Qué semestre está activo, cuáles existen y cómo se crean.

Esta lógica estaba escrita **tres veces** —`tests_semanales/src/config.py`,
`tareas/src/config.py` y `app/utils/runner.py`— las tres con un comentario
"mantener sincronizado con...". Ese comentario era la señal de que faltaba
este módulo.

## Qué hace y qué no

**Sí:** leer y escribir `semestres/activo.txt`, listar los semestres, crear uno
nuevo desde la plantilla, y resolver las rutas de datos y prompts.

**No:** leer o escribir los CSV de adentro (eso es de `datos`), ni saber qué es
una semana o una tarea.

## Importaciones permitidas

Solo librería estándar. Es el módulo más básico: no importa ningún otro.

## Cómo se usa

```python
from modulos import semestre

semestre.activo()            # "2026-2", o None si no hay ninguno
semestre.activo_o_error()    # igual, pero falla con mensaje claro si no hay
semestre.listar()            # ["2025-2", "2026-1", "2026-2"]
semestre.crear("2027-1")     # copia la plantilla con los datos del curso; NO lo activa
semestre.activar("2027-1")

semestre.datos("tests_semanales")    # .../semestres/2026-2/tests_semanales/data
semestre.prompts("tareas")
```

## Por qué dos formas de pedir el activo

`activo()` devuelve `None` cuando no hay ninguno: lo usa la app, que necesita
mostrar "crea tu primer semestre" en vez de reventar.

`activo_o_error()` lanza excepción: lo usan los scripts, que corren sin
interfaz y deben cortar de inmediato con un mensaje entendible.

## La variable IN5162_SEMESTRE

`IN5162_SEMESTRE` gana por sobre el `activo.txt` y vale solo para el proceso que
la define. Existe para que las pruebas trabajen sobre una copia desechable sin
escribir el archivo, que es compartido: antes lo modificaban y lo restauraban al
terminar, así que una prueba interrumpida a mitad dejaba al sistema apuntando a
un semestre borrado. Peor todavía, la prueba que ejecuta las páginas de la app
llegó a dejar activo un semestre histórico, y el chequeo del día siguiente
revisó el curso equivocado.

Para uso manual sirve igual, sin dejar rastro:

```bash
IN5162_SEMESTRE=2026-1 python -m modulos.tests.resumen 3
```

## Cuidado

`crear()` copia desde `semestres/_template/`, **nunca** desde el semestre
activo. Es a propósito: un semestre nuevo tiene que empezar sin datos de
alumnos del anterior.

Los prompts y correos de la plantilla tienen marcas donde va el curso: «CURSO»,
«NOMBRE_CURSO» y «FIRMA». `crear()` las llena con esas claves del `.env`
(CURSO, si falta, es IN5162; FIRMA, si falta, es «Equipo» y el código) y, si
falta NOMBRE_CURSO, no crea el semestre: el error dice qué agregar. `modulos.web.subir` e `instalar.py` las llenan igual al
subir la plantilla al sitio.
