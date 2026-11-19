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
| `simulaciones.py` | que ningún flujo en modo prueba escriba `notas.csv` ni el log |
| `comun.py` | el andamiaje compartido; no es una prueba |

`e2e_tests_semanales.py` tiene dos partes. La primera es el curso funcionando
bien: se manda la pregunta, se evalúa, y ni el envío ni la evaluación se repiten
si el comando se corre dos veces. La segunda reproduce los tres problemas que ya
ocurrieron de verdad — los envíos hechos desde otro equipo, el proceso muerto a
mitad de la evaluación, y la red cortada justo al marcar los correos como
leídos— y comprueba que en ninguno se pierda una nota ya pagada a la API.

## Al agregar una prueba

Usar el andamiaje de `comun.py`: `semestre_desechable()` para la copia,
`sin_red()` para bloquear SMTP e IMAP, `check()` para cada verificación y
`resultado()` al final. Después sumar el archivo a la lista de `todas.py`.
