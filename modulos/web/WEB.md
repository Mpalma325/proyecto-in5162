# Módulo `web`

Lo que conecta este equipo con el sitio web del curso (`web/` en la raíz del
repositorio; ver `web/SITIO.md`).

## Qué hace y qué no

**Sí:** subir al sitio el panel de cada semestre, la tabla que arma
`datos.reportes.panel()`. Con `--archivos`, además, copiar a R2 las carpetas
completas de cada semestre y la plantilla de semestres nuevos: es la migración
inicial, y desde ahí el motor las mantiene al día.

**No:** mandar correos, llamar al modelo ni modificar los CSV del disco. `bajar` deja
sus copias en `respaldos/`, nunca en `semestres/`.

## Importaciones permitidas

`modulos.datos`, `modulos.semestre` y `modulos.config`. No importa `mail` ni `ia`.

## Por qué el sitio calcula igual que los scripts

La página no reimplementa las métricas. Carga `modulos/datos/agregaciones.py` y
lo corre en el navegador con Pyodide. Por eso ese archivo no puede importar nada
del proyecto: si lo hace, la página deja de funcionar. `npm run preparar`, en
`web/`, copia la versión vigente antes de cada despliegue.

## Acceso

- Las personas entran por Cloudflare Access. El Worker rechaza cualquier lectura
  que no traiga el encabezado de Access, así que si alguien despliega sin
  configurarlo, la página queda sin datos en vez de quedar abierta.
- Este equipo sube con `WEB_TOKEN`, que debe coincidir con el secreto
  `TOKEN_MOTOR` del Worker: sube como si fuera el motor. Ese token no sirve para
  ver la reportería ni para pedir trabajos.

## Uso

```bash
python -m modulos.web.subir --simular   # qué subiría
python -m modulos.web.subir             # sube el panel de todos los semestres
python -m modulos.web.subir --archivos  # además, los archivos y la plantilla a R2
python -m modulos.web.bajar 2026-2 --comparar  # qué difiere entre la nube y este equipo
python -m modulos.web.bajar 2026-2      # respaldo en respaldos/web/<fecha>/
```

Con `--archivos` se suben los datos de los alumnos. Hacia el sitio publicado,
eso se hace una vez y a propósito.
