"""Segunda oportunidad de tareas, con correo y modelo simulados."""

import csv
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, 'pruebas')
from comun import check, resultado, semestre_desechable, titulo


def rechaza(nombre, llamada):
    try:
        llamada()
    except ValueError:
        check(nombre, True)
    else:
        check(nombre, False)


with semestre_desechable(base='_template', sid='_tmp_segunda_oportunidad') as (sid, tmp), \
        patch('socket.create_connection', side_effect=AssertionError('Red bloqueada')):
    from modulos import datos
    from modulos.tareas import config, storage, reporte, segunda_oportunidad as segunda
    from modulos.tareas import corregir, recolectar
    from modulos.tareas.escala import validar_nota

    # Ana respondió y tiene nota; Beto y Carla recibieron y no respondieron;
    # a Dora nunca se le envió.
    filas = [dict(tarea='T1', grupo_archivo='grupo.html', alumno_nombre=nombre,
                  alumno_correo=f'{nombre.lower()}@example.test', pregunta_tarea='P1',
                  pregunta=f'Pregunta original de {nombre}', pauta='Pauta original',
                  message_id=f'<original-{nombre}@example.test>')
             for nombre in ('Ana', 'Beto', 'Carla', 'Dora')]
    storage.escribir_csv('T1', filas)
    for f in filas[:3]:
        datos.notas.marcar_enviado(f['alumno_correo'], datos.TAREAS, 'T1')
    datos.notas.marcar_respondio(filas[0]['alumno_correo'], datos.TAREAS, 'T1')
    datos.notas.registrar_nota(filas[0]['alumno_correo'], datos.TAREAS, 'T1', '0.0')
    notas_antes = (tmp / 'notas.csv').read_bytes()
    (config.PROMPTS / 'correo_segunda_oportunidad.md').write_text(
        'Hola {nombre}, pregunta sobre la {pregunta_tarea}:\n\n{pregunta}\n\n'
        'Plazo: hasta las 10:25. Si no respondes, tendrás que entrevistarte con el profesor.',
        encoding='utf-8')

    titulo('Lista de notas para el equipo')
    informe, pendientes = reporte.exportar('T1')
    with informe.open(encoding='utf-8-sig') as fh:
        salida = list(csv.DictReader(fh))
    check('distingue cero de pendiente', salida[0]['Ajuste en nota'] == '0,0'
          and salida[1]['Ajuste en nota'] == '')
    with pendientes.open(encoding='utf-8-sig') as fh:
        check('lista solo a los enviados sin respuesta', len(list(csv.DictReader(fh))) == 2)

    titulo('Preparar: a quiénes y con qué pregunta')

    NUEVA = {'Beto': '¿Qué cambia si escalas la edad antes de ajustar el modelo lineal?',
             'Carla': '¿Por qué filtraste los colegios con menos de treinta alumnos?'}

    def modelo(system, user, json_mode=True):
        nombre = 'Beto' if 'Beto' in user.split('\n')[1] else 'Carla'
        return MagicMock(datos={'integrantes': [{
            'nombre': nombre, 'pregunta_tarea': 'P1',
            'pregunta': NUEVA[nombre], 'pauta': f'Pauta nueva de {nombre}'}]})

    secciones = ({'p1': 'código de la P1', 'p2': '', 'p3': '', 'p4': '', 'roles_html': ''}, [], 'grupo.html')
    with patch.object(segunda, '_leer_entrega', return_value=secciones), \
            patch.object(segunda.ia, 'completar', side_effect=modelo) as ia:
        plan = segunda.preparar('T1')
        check('elige solo a quienes recibieron y no respondieron',
              [a['nombre'] for a in plan] == ['Beto', 'Carla'], [a['nombre'] for a in plan])
        check('una llamada al modelo por alumno', ia.call_count == 2, ia.call_count)
        pedido = ia.call_args_list[0].args[1]
        check('pide evitar lo que ya se preguntó al grupo',
              all(f'Pregunta original de {n}' in pedido for n in ('Ana', 'Beto', 'Carla')))
        check('manda solo la parte que le toca', 'código de la P1' in pedido)
        segunda.preparar('T1')
        check('correrlo de nuevo no regenera', ia.call_count == 2, ia.call_count)
    with patch.object(segunda, '_leer_entrega', return_value=secciones), \
            patch.object(segunda.ia, 'completar', side_effect=[
                MagicMock(datos={'integrantes': [{'pregunta': 'Pregunta original de Beto?', 'pauta': 'x'}]}),
                MagicMock(datos={'integrantes': [{'pregunta': NUEVA['Carla'], 'pauta': 'y'}]})]) as ia:
        p, _ = segunda._pregunta_nueva('T1', plan[0], ['Pregunta original de Beto'])
        check('si repite la original, pide otra', ia.call_count == 2 and p == NUEVA['Carla'])
    check('preparar no toca notas', (tmp / 'notas.csv').read_bytes() == notas_antes)
    check('la pregunta original sigue en feedback hasta enviar',
          storage.leer_csv('T1')[1]['pregunta'] == 'Pregunta original de Beto')

    borrador = segunda.borradores('T1').read_text(encoding='utf-8')
    check('borrador con pregunta, plazo y entrevista',
          NUEVA['Beto'] in borrador and '10:25' in borrador and 'entrevistarte' in borrador)
    check('la pauta no va en el correo', 'Pauta nueva' not in borrador)

    titulo('Enviar')
    with patch.object(segunda, 'enviar_correo', side_effect=['<nueva-beto@t>', '<nueva-carla@t>']) as smtp:
        segunda.enviar('T1')
        check('un correo a cada uno', smtp.call_count == 2, smtp.call_count)
        segunda.enviar('T1')
        check('correrlo de nuevo no repite correos', smtp.call_count == 2, smtp.call_count)
    fb = {f['alumno_nombre']: f for f in storage.leer_csv('T1')}
    check('feedback queda con la pregunta, pauta e id nuevos',
          fb['Beto']['pregunta'] == NUEVA['Beto']
          and fb['Beto']['pauta'] == 'Pauta nueva de Beto'
          and fb['Beto']['message_id'] == '<nueva-beto@t>')
    check('a quien ya respondió no se le toca', fb['Ana']['pregunta'] == 'Pregunta original de Ana')
    check('la original queda guardada',
          segunda.leer('T1')[0]['pregunta_original'] == 'Pregunta original de Beto')

    titulo('Recolectar y corregir, los de siempre')
    with patch.object(recolectar, 'buscar_respuestas',
                      return_value={'<nueva-beto@t>': {'remitente': 'beto@example.test',
                                                       'texto': 'Mi respuesta.',
                                                       'fecha': '2026-09-25T10:20:00'}}) as buscar:
        recolectar.main('T1')
        ids = buscar.call_args.args[0]
        check('busca respuestas al correo nuevo, no al original',
              {'<nueva-beto@t>', '<nueva-carla@t>'} <= set(ids)
              and '<original-Beto@example.test>' not in ids, ids)
    (config.PROMPTS / 'correo_feedback.md').write_text(
        'Hola {nombre}:\n{comentario}\nAjuste a la nota de la tarea: {ajuste} puntos',
        encoding='utf-8')
    (config.PROMPTS / 'escala.json').write_text('{"valores": [-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3]}', encoding='utf-8')
    with patch.object(corregir, 'OpenAI'), patch.object(corregir.config, 'cargar_api_key', return_value='falsa'), \
            patch.object(corregir, '_corregir_una', return_value={'nota': 6, 'comentario': 'Escala vieja'}), \
            patch.object(corregir, 'enviar_correo') as smtp:
        corregir.main('T1')
        check('no registra ni comunica una nota fuera de escala',
              not datos.notas.ya_evaluado('beto@example.test', datos.TAREAS, 'T1') and not smtp.called)
    with patch.object(corregir, 'OpenAI'), patch.object(corregir.config, 'cargar_api_key', return_value='falsa'), \
            patch.object(corregir, '_corregir_una', return_value={'nota': 0.2, 'comentario': 'Bien.'}) as corrector, \
            patch.object(corregir, 'enviar_correo') as smtp:
        corregir.main('T1')
        check('corrige contra la pregunta y pauta nuevas',
              corrector.call_args.args[2]['pregunta'] == NUEVA['Beto']
              and corrector.call_args.args[2]['pauta'] == 'Pauta nueva de Beto')
        check('el feedback dice el ajuste con signo', '+0,2' in smtp.call_args.args[2], smtp.call_args)
    check('nota nueva sin tocar a quien ya tenía',
          datos.notas.estado('beto@example.test', datos.TAREAS, 'T1')['Nota'] == '0.2'
          and datos.notas.estado('ana@example.test', datos.TAREAS, 'T1')['Nota'] == '0.0')

    titulo('Escala')
    rechaza('rechaza la escala antigua', lambda: validar_nota(6))
    rechaza('rechaza puntajes entre escalones', lambda: validar_nota(0.15))
    rechaza('rechaza NaN', lambda: validar_nota(float('nan')))
    check('acepta extremos y cero', all(validar_nota(v) == v for v in (-0.3, 0, 0.3)))

sys.exit(resultado())
