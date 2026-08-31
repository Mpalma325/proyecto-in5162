# Módulo `tests`

El flujo de los Tests Semanales: mandar la pregunta de la semana, evaluar lo
que responden los alumnos y resumir cómo le fue al curso.

## Qué hace y qué no

**Sí:** decidir a quién le toca qué pregunta según su grupo, armar el correo,
interpretar la evaluación que devuelve el modelo y coordinar el registro.

**No:** hablar SMTP/IMAP (eso es `mail`), llamar a la API (eso es `ia`), ni
escribir CSV a mano (eso es `datos`). Este módulo **sí** puede importar a los
tres: es un flujo, y orquestar es justamente su trabajo.

## Los pasos

| Archivo | Qué hace |
|---|---|
| `enviar.py` | Manda la pregunta de la semana a quien todavía no la tiene |
| `evaluar.py` | Lee las respuestas del buzón, las evalúa y devuelve el feedback |
| `resumen.py` | Resume cómo le fue al curso esa semana |
| `chequeo.py` | Dice qué pasaría al evaluar, **sin enviar nada** |
| `reconstruir.py` | Rearma el historial leyendo el buzón, cuando el registro local se perdió |

Auxiliares: `preguntas.py` (lee `preguntas.csv`), `storage.py` (el formato
viejo, en retirada), `ia_prompts.py` (los prompts de este flujo),
`config.py` (proxy al config del subproyecto, donde está el `.env`).

## Cómo se ejecuta

Desde la raíz del proyecto:

```
python -m modulos.tests.chequeo 4        # no manda nada
python -m modulos.tests.enviar 4
python -m modulos.tests.evaluar 4
python -m modulos.tests.resumen 4
```

La app invoca exactamente estos mismos comandos como subprocesos, así que
correrlos a mano o desde la interfaz hace lo mismo.

## Cuidado

**`enviar` y `evaluar` mandan correos reales.** Para probar, usar `--dry-run` o
las pruebas de `pruebas/`, que mockean SMTP e IMAP.

Al evaluar, la nota se guarda **apenas se corrige a cada alumno**, no al final.
Es a propósito: si el proceso muere a mitad, el correo ya salió y la API ya se
gastó, así que perder esa nota obligaría a repetir todo. Si cambias eso, se
pierde esa garantía.

Para decidir a quién enviar se cruzan los dos esquemas de datos: basta que uno
diga "ya se envió" para no reenviar. Es deliberadamente conservador — un correo
repetido al alumno es peor que un envío de menos.
