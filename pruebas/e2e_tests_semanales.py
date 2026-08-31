"""
Ciclo completo de Tests Semanales, más los escenarios en que algo falla.

Corre sobre una copia desechable del semestre, con SMTP, IMAP y el modelo
simulados: no manda un solo correo ni gasta un token.

La segunda parte reproduce lo que pasa de verdad al operar el curso entre dos
personas: los envíos se hicieron en otro equipo, el proceso se cae a mitad, la
red se corta justo al final. Cada uno de esos casos corresponde a algo que ya
ocurrió.
"""

import sys
from unittest.mock import patch

sys.path.insert(0, "pruebas")
from comun import (check, enviados, nota_ia, resultado, respuestas_falsas,
                   semestre_desechable, sin_red, titulo)

TRES_TABLAS = ("alumnos.csv", "notas.csv", "log_envios.csv")


def ciclo_completo():
    """Semestre recién abierto: envío, evaluación, y que nada se repita."""
    with semestre_desechable(sid="_tmp_e2e", vaciar=TRES_TABLAS) as (sid, tmp), sin_red():
        from modulos import datos
        from modulos.tests import enviar, evaluar

        titulo("1. ENVIO semana 5 (nueva)")
        enviar.main(5, dry_run=False)
        check("envio a los 36", len(enviados) == 36, len(enviados))
        check("notas.csv registro 36",
              sum(1 for f in datos.notas.leer(sid, datos.TESTS, "5") if f["Enviado"]) == 36)
        check("log: 36 eventos de envio",
              len(datos.log.leer(sid, evento="envio", item="5")) == 36)

        titulo("2. REENVIO (no debe mandar nada)")
        enviados.clear()
        enviar.main(5, dry_run=False)
        check("no reenvio", len(enviados) == 0, enviados[:3])

        titulo("3. EVALUACION de 2 respuestas")
        correos = datos.alumnos.correos(sid)[:2]
        entrantes = respuestas_falsas(correos, 5)
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=entrantes), \
             patch("modulos.tests.evaluar.evaluar_respuesta", return_value=nota_ia("6,5", "Baja")):
            evaluar.main(5, dry_run=False)
        check("feedback a los 2", len(enviados) == 2, enviados)
        estado = datos.notas.estado(correos[0], datos.TESTS, "5", sid)
        check("nota guardada", estado and estado["Nota"] == "6,5", estado)
        check("log: 2 evaluaciones",
              len(datos.log.leer(sid, evento="evaluacion", item="5")) == 2)

        titulo("4. RE-EVALUACION (a quien ya tiene nota no se le vuelve a cobrar la API)")
        llamadas = []
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=entrantes), \
             patch("modulos.tests.evaluar.evaluar_respuesta",
                   side_effect=lambda *a: (llamadas.append(1), nota_ia("7,0"))[1]):
            evaluar.main(5, dry_run=False)
        check("no re-llamo a la IA", len(llamadas) == 0, len(llamadas))
        check("nota intacta",
              datos.notas.estado(correos[0], datos.TESTS, "5", sid)["Nota"] == "6,5")


def _vaciar_semana(carpeta, semana):
    """Borra de la copia las notas y los eventos de esa semana de tests."""
    import csv as _csv

    notas = carpeta / "notas.csv"
    with notas.open(encoding="utf-8-sig", newline="") as f:
        lector = _csv.DictReader(f)
        campos, filas = lector.fieldnames, list(lector)
    filas = [x for x in filas
             if not (x["Flujo"] == "test" and x["Item"] == str(semana))]
    with notas.open("w", encoding="utf-8", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)

    log = carpeta / "log_envios.csv"
    if log.exists():
        with log.open(encoding="utf-8-sig", newline="") as f:
            lector = _csv.DictReader(f)
            campos, filas = lector.fieldnames, list(lector)
        filas = [x for x in filas
                 if not (x.get("Flujo") == "test" and x.get("Item") == str(semana))]
        with log.open("w", encoding="utf-8", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(filas)


def fallos_y_recuperacion():
    """Semestre en curso: los envíos los hizo otra persona y las cosas se caen."""
    SEM = 4
    with semestre_desechable(sid="_tmp_fallos") as (sid, tmp), sin_red():
        # La semana de prueba se deja sin evaluar. Antes se daba por hecho que
        # estaba vacía, y la prueba empezó a fallar el día que el curso la
        # evaluó de verdad: dependía del estado real del semestre.
        _vaciar_semana(tmp, SEM)
        from modulos import datos
        import modulos.mail.lectura as lectura
        from modulos.tests import evaluar

        curso = datos.alumnos.correos(sid)

        titulo("6. identifica a los alumnos sin tener los message_ids del otro equipo")
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(curso, SEM, cantidad=5)), \
             patch("modulos.tests.evaluar.evaluar_respuesta", return_value=nota_ia()):
            evaluar.main(SEM, dry_run=False)
        check("identifico y evaluo los 5 por remitente", len(enviados) == 5, enviados)
        check("notas guardadas",
              sum(1 for f in datos.notas.leer(sid, datos.TESTS, str(SEM)) if f["Nota"]) == 5)

        titulo("7. el proceso MUERE a mitad (falla la IA en el 3ro de 4)")
        llamadas = []

        def ia_que_falla(*a):
            llamadas.append(1)
            if len(llamadas) == 3:
                raise RuntimeError("timeout de OpenAI")
            return nota_ia("5,5", "Baja")

        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(curso, SEM, desde=5, cantidad=4)), \
             patch("modulos.tests.evaluar.evaluar_respuesta", side_effect=ia_que_falla):
            evaluar.main(SEM, dry_run=False)
        hechas = sum(1 for f in datos.notas.leer(sid, datos.TESTS, str(SEM)) if f["Nota"])
        check("lo evaluado antes del fallo NO se perdio", hechas == 8, hechas)

        titulo("8. al reanudar, solo evalua al que falto")
        llamadas.clear()
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(curso, SEM, desde=5, cantidad=4)), \
             patch("modulos.tests.evaluar.evaluar_respuesta",
                   side_effect=lambda *a: (llamadas.append(1), nota_ia())[1]):
            evaluar.main(SEM, dry_run=False)
        check("solo re-llamo a la IA 1 vez", len(llamadas) == 1, len(llamadas))
        check("total evaluados ahora 9",
              sum(1 for f in datos.notas.leer(sid, datos.TESTS, str(SEM)) if f["Nota"]) == 9)

        titulo("9. se cae la red al marcar leidos (ya pasó una vez)")
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(curso, SEM, desde=9, cantidad=2)), \
             patch("modulos.tests.evaluar.evaluar_respuesta", return_value=nota_ia("7,0", "Alta")), \
             patch.object(lectura, "marcar_leidos",
                          side_effect=OSError("[Errno 11001] getaddrinfo failed")):
            evaluar.main(SEM, dry_run=False)
        check("no revento pese al fallo de red", True)
        check("las 2 notas nuevas quedaron guardadas",
              sum(1 for f in datos.notas.leer(sid, datos.TESTS, str(SEM)) if f["Nota"]) == 11)


ciclo_completo()
fallos_y_recuperacion()
sys.exit(resultado())
