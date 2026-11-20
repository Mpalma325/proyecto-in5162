# Pruebas

Corren el sistema de verdad —los mismos módulos que operan el curso— pero sobre
una copia desechable del semestre, con el correo y el modelo simulados. No sale
un solo mensaje ni se gasta un token, y la copia se borra al terminar.

```bash
python pruebas/todas.py
```

Ninguna toca el `activo.txt`. El semestre de trabajo se fija con la variable de
entorno `IN5162_SEMESTRE`, que vive solo en ese proceso; antes se escribía el
archivo compartido y se restauraba al final, y una prueba interrumpida a mitad
dejaba al sistema apuntando a una carpeta borrada.

## Qué cubre cada una

| Archivo | Qué verifica |
|---|---|
| `e2e_tests_semanales.py` | el ciclo de tests, y qué pasa cuando algo se cae |
| `e2e_tareas.py` | el ciclo de tareas, y que no pise los datos de los tests |
| `simulaciones.py` | que ningún flujo en modo prueba escriba `notas.csv`, el log ni `escala_notas.json` |
| `escala.py` | la escala de notas de Tests (redondeo, inversa, dos tramos) y el trabajo `datos.escala`: lo que dice la simulación, el recálculo de verdad, las notas que quedan fijas y la confirmación de la página |
| `correccion.py` | la corrección en JSON: puntajes, nota calculada con la escala y lo que muestra el correo con `nota`, `puntajes` y `nada`; compara la versión de Python con la de la página (`web/public/correccion.js`, `escala.js`) |
| `comun.py` | el andamiaje compartido; no es una prueba |

`e2e_tests_semanales.py` tiene dos partes. La primera es el curso funcionando
bien: se manda la pregunta, se evalúa, y ni el envío ni la evaluación se repiten
si el comando se corre dos veces. La segunda reproduce los tres problemas que ya
ocurrieron de verdad — los envíos hechos desde otro equipo, el proceso muerto a
mitad de la evaluación, y la red cortada justo al marcar los correos como
leídos— y comprueba que en ninguno se pierda una nota ya pagada a la API.

Las que comparan Python con JavaScript corren Node con un script de
`web/scripts/` (`probar-correccion.mjs`, `probar-revision.mjs`, …): le pasan
una lista de llamadas en un JSON y comparan lo que devuelve con lo que da el
módulo de Python con los mismos argumentos. Sin Node, esas verificaciones
fallan.

`correccion.py` evalúa sobre una copia de 2026-2 a la que le agrega
`configuracion.json` y `escala_notas.json`; `escala.py` trabaja sobre copias
de la plantilla. 2026-2 no tiene esos archivos: ahí todo tiene que dar lo
mismo que antes, y las pruebas de cuerpo idéntico lo verifican.

## Al agregar una prueba

Usar el andamiaje de `comun.py`: `semestre_desechable()` para la copia,
`sin_red()` para bloquear SMTP e IMAP, `check()` para cada verificación y
`resultado()` al final. Después sumar el archivo a la lista de `todas.py`.
