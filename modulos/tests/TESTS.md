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
| `feedback.py` | Manda las correcciones que el docente aprobó en Tests › Revisar |
| `resumen.py` | Resume cómo le fue al curso esa semana |
| `chequeo.py` | Dice qué pasaría al evaluar, **sin enviar nada** |
| `tutoria.py` | Responde las dudas del alumno sobre su corrección. **No cambia la nota.** |
| `reconstruir.py` | Rearma el historial leyendo el buzón, cuando el registro local se perdió |
| `experimento.py` | Reevalúa respuestas viejas con otro prompt, para comparar. **No manda nada** |

Auxiliares: `preguntas.py` (lee `preguntas.csv`), `storage.py` (el formato
viejo, en retirada), `ia_prompts.py` (los prompts de este flujo),
`correccion.py` (lee la corrección y calcula la nota, ver abajo),
`decisiones.py` (lo que decidió el docente en la revisión),
`config.py` (proxy al config del subproyecto, donde está el `.env`).

## La corrección y la nota

Hay dos formatos de corrección y `correccion.py` los distingue por el
contenido. En el viejo (2026-2 y anteriores) el modelo escribe un HTML con
`NOTA FINAL`, y esa es la nota. En el nuevo el prompt pide JSON: el modelo
devuelve el puntaje de cada pregunta (0; 0,5; 1; 2 o 3) y no escribe nota. El
código valida cada puntaje, calcula el logro (puntos sobre el máximo) y lo pasa
por la escala del semestre (`escala_notas.json`, `modulos/escala.py`). Un
puntaje fuera de la rúbrica deja la corrección sin nota y por revisar: no sale
ningún correo con ella.

`ia_prompts.py` pide `json_mode` a la API solo cuando el prompt dice «JSON».
Un semestre con el prompt viejo sigue igual que siempre.

`correo_muestra` (configuracion.json) decide qué números ve el alumno:
`nota`, `puntajes` o `nada`. La nota se registra igual en los tres casos.
El equipo docente ve siempre la corrección completa (`texto_docente`).

La escala se cambia desde Configuración › Semestre, con el trabajo
`datos.escala` (modulos/datos/DATOS.md). Las notas de Tests ya registradas se
recalculan con la escala nueva; cada evaluación queda con la escala con que se
calculó (`escala=` en Versiones).

`web/public/correccion.js` es la gemela para la página y
`pruebas/correccion.py` compara las dos sobre los mismos casos.

## Cómo se ejecuta

Desde la raíz del proyecto:

```
python -m modulos.tests.chequeo 4        # no manda nada
python -m modulos.tests.enviar 4
python -m modulos.tests.evaluar 4
python -m modulos.tests.resumen 4
python -m modulos.tests.experimento --prompt candidato.md -n 20
```

La app invoca exactamente estos mismos comandos como subprocesos, así que
correrlos a mano o desde la interfaz hace lo mismo.

## La tutoría

El alumno recibe su nota y escribe de vuelta preguntando por qué. Eso no es una
respuesta atrasada y no debe tratarse como tal: se reconoce porque su
`In-Reply-To` apunta al Message-ID de una evaluación o una tutoría nuestra.

Por eso `evaluar` guarda el Message-ID del feedback que envía. Antes lo
generaba y lo descartaba, y sin ese ancla una repregunta era indistinguible de
una respuesta fuera de plazo: el alumno recibía un "ya respondiste, no se te
puede evaluar en una segunda ocasión" y su texto se perdía.

`evaluar` detecta esos correos y los deja **sin leer** para que los recoja
`tutoria`, que corre aparte y cuando uno quiera.

Reglas que no hay que romper al tocarlo:

- **La nota no se modifica nunca.** El prompt lo prohíbe explícitamente y el
  flujo no llama a `notas.registrar_nota`. Si alguna vez se quisiera permitir
  recorregir, es otra funcionalidad y merece su propio comando.
- Se corta a `MAX_RONDAS` vueltas por alumno y semana, para que una duda no se
  convierta en una negociación indefinida.
- El modelo recibe la pregunta, la pauta, lo que respondió el alumno, la
  corrección que se le mandó y el historial. Sin ese contexto no puede explicar
  por qué le faltó puntaje.

## El ensayo de prompts

`experimento.py` contesta una pregunta que antes había que responder a ojo: si
se cambia el prompt de evaluación, ¿cómo se mueve lo que el modelo califica?

Toma N respuestas al azar entre las que ya tienen nota, las vuelve a pasar por
el modelo con un prompt candidato y compara casilla por casilla contra la nota
y la originalidad que propuso el modelo en su momento (`NotaAntes`). Si el
docente la cambió en la revisión o con un ajuste, la nota que quedó va al lado,
en `NotaFinal`. Las casillas que el docente corrigió a mano no entran en la
muestra. La muestra sale del mismo
`reportes.panel()` que alimenta los gráficos, así que "lo que se evaluó"
significa lo mismo acá que allá.

El muestreo va con semilla. Dos corridas con la misma semilla eligen las mismas
respuestas, que es lo que permite comparar dos prompts entre sí en vez de
comparar dos muestras distintas.

Las tres cosas que no hace, y que conviene dejar así:

- **No manda correos.** El alumno ya recibió su feedback; esto es un ensayo.
- **No toca `notas.csv`.** La nota comunicada es la que vale.
- **No escribe en el log.** El log es la historia del curso, y una prueba de
  laboratorio no es un evento del curso. El resultado va a un CSV propio,
  `experimento_<fecha>.csv`, en la carpeta de datos del semestre.

El prompt candidato se le pasa como archivo y llega a `evaluar_respuesta()` por
el parámetro `plantilla`. El archivo del semestre no se toca: la evaluación real
sigue usando el de siempre hasta que alguien lo edite a mano.

Si el prompt candidato no pide JSON y no menciona `NOTA FINAL:` ni
`ORIGINALIDAD:`, avisa antes de empezar. Sin esas etiquetas
`extraer_nota_y_originalidad` no encuentra nada y la comparación sale vacía
después de haber gastado la API. Con un prompt JSON la nota nueva la calcula
el código con la escala del semestre, igual que al corregir.

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
