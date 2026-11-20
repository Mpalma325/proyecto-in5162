# 2. Cuentas y claves

Esta página se hace en orden, porque el correo del curso se usa para crear las otras tres cuentas. Trabaja en una ventana privada del navegador (en Chrome, Ctrl+Shift+N) o en un perfil de navegador donde solo esté abierta la cuenta del curso: así ninguna página toma por error tu cuenta personal. Al final de cada sección se indica qué copiar en la hoja de datos.

## 2.1 El correo del curso

### Crear la cuenta

Si el curso ya tiene un Gmail propio, salta a la sección siguiente.

1. Entra a `accounts.google.com/signup`.
2. Crea la cuenta, por ejemplo `curso.abc123@gmail.com`. Google pide un número de teléfono.
3. Deja la sesión abierta en esta ventana.

### Activar la verificación en dos pasos

Gmail solo entrega contraseñas de aplicación a cuentas con verificación en dos pasos.

1. Entra a `myaccount.google.com` con la cuenta del curso.
2. Abre la sección de seguridad y luego «Verificación en dos pasos».
3. Actívala y sigue los pasos: Google manda un código al teléfono y pide escribirlo.
4. Al terminar, la página indica que la verificación en dos pasos está activada.

### Crear la contraseña de aplicación

1. Entra a `myaccount.google.com/apppasswords`. Google puede pedir de nuevo la contraseña de la cuenta.
2. En «Nombre de la app» escribe `Curso ABC123` y haz clic en «Crear».
3. Google muestra una contraseña de 16 letras en cuatro grupos, por ejemplo `abcd efgh ijkl mnop`. Cópiala en la hoja de datos. Los espacios no importan: el instalador los quita.
4. Haz clic en «Listo». Google no vuelve a mostrar esa contraseña; si la pierdes, crea otra y borra la anterior desde la misma página.

Si `myaccount.google.com/apppasswords` dice que la opción no está disponible para tu cuenta, hay dos causas posibles: la verificación en dos pasos no quedó activada (vuelve a la sección anterior), o la cuenta pertenece a una organización, como una universidad, que desactivó las contraseñas de aplicación. En el segundo caso usa una cuenta @gmail.com.

Google anula todas las contraseñas de aplicación cuando se cambia la contraseña de la cuenta. Si algún día la cambias, crea una contraseña de aplicación nueva y cárgala como dice la página 5.

**Copia en la hoja de datos:** el correo del curso y la contraseña de aplicación.

## 2.2 OpenAI

### Crear la cuenta y cargar saldo

1. Entra a `platform.openai.com` y crea una cuenta con el correo del curso («Sign up»; sirve «Continue with Google»). OpenAI puede pedir un teléfono.
2. Abre «Settings» (el engranaje, arriba a la derecha) y luego «Billing».
3. Haz clic en «Add payment details», ingresa la tarjeta y elige el monto inicial del saldo.
4. Deja apagada la recarga automática («auto recharge»). Con el saldo prepagado y sin recarga, el gasto nunca pasa de lo que cargaste. Cuando el saldo se acaba, las correcciones fallan hasta que cargues más.

### Crear la clave

1. Entra a `platform.openai.com/api-keys`.
2. Haz clic en «Create new secret key».
3. En «Name» escribe `ABC123 curso`. Deja «Project» en el proyecto por defecto y «Permissions» en «All».
4. Haz clic en «Create secret key» y luego en «Copy». La clave empieza con `sk-`. OpenAI no la vuelve a mostrar.

El instalador comprueba que la clave funciona, pero esa prueba no gasta saldo y no detecta si el saldo está en cero. Carga el saldo antes de la página 4.

**Copia en la hoja de datos:** la clave de OpenAI.

## 2.3 Cloudflare

Los rótulos de Cloudflare van en inglés, el idioma por defecto de su panel.

### Crear la cuenta

1. Entra a `dash.cloudflare.com/sign-up` y crea la cuenta con el correo del curso.
2. Abre el correo de Cloudflare que llega al Gmail del curso y confirma la dirección.
3. Si el panel ofrece agregar un dominio o un sitio, sáltalo. El sistema usa una dirección gratuita de workers.dev.

### Copiar el Account ID

El Account ID son 32 caracteres, números y letras de la a a la f.

1. Con la sesión iniciada, mira la barra de direcciones del navegador: queda como `https://dash.cloudflare.com/` seguido de esos 32 caracteres y una barra.
2. Si prefieres copiarlo desde el panel, abre «Workers & Pages» en el menú izquierdo: el Account ID aparece en la columna derecha, con un botón para copiarlo.

**Copia en la hoja de datos:** el Account ID.

### Activar R2

R2 es el almacenamiento donde quedan los archivos de cada semestre. Se activa una vez por cuenta.

1. En el menú izquierdo, abre «R2 Object Storage».
2. Sigue el paso que ofrece el panel para activar R2 con el plan gratuito (10 GB). Cloudflare puede pedir una tarjeta o PayPal aunque el plan no cobre.
3. No crees ningún bucket: lo crea el instalador.

### Activar Zero Trust

Zero Trust es la parte de Cloudflare que da Access, el control de quién entra al sitio.

1. En el menú izquierdo, abre «Zero Trust», o entra directo a `one.dash.cloudflare.com`.
2. Elige el nombre del equipo («team name»), por ejemplo `abc123-curso`. Ese nombre forma la dirección de la página donde el equipo docente inicia sesión: `abc123-curso.cloudflareaccess.com`.
3. Elige el plan «Free» (hasta 50 personas). Cloudflare puede pedir un medio de pago aunque el plan cueste 0.
4. No configures nada más: el instalador crea la aplicación y la regla de acceso.

### Crear el token de la API

El instalador usa este token para crear y publicar el sitio, y revisa uno por uno los cinco permisos de abajo: si falta alguno, dice cuál.

1. Entra a `dash.cloudflare.com/profile/api-tokens` (también se llega desde el ícono de usuario, arriba a la derecha, «My Profile» y luego «API Tokens»).
2. Haz clic en «Create Token».
3. Al final de la lista de plantillas, en «Custom token», haz clic en «Get started».
4. En «Token name» escribe `Instalador ABC123`.
5. En «Permissions» arma estas cinco filas. Cada fila tiene tres listas: en la primera elige «Account», en la segunda el permiso y en la tercera «Edit». Para cada fila nueva, haz clic en «+ Add more».

   | Primera lista | Segunda lista | Tercera lista |
   |---|---|---|
   | Account | Workers Scripts | Edit |
   | Account | D1 | Edit |
   | Account | Workers R2 Storage | Edit |
   | Account | Access: Apps and Policies | Edit |
   | Account | Access: Organizations, Identity Providers, and Groups | Edit |

6. En «Account Resources» deja «Include» y elige la cuenta del curso.
7. Deja el resto como está y haz clic en «Continue to summary» y luego en «Create Token».
8. Copia el token. Cloudflare no lo vuelve a mostrar. La página ofrece además un comando para probarlo: no hace falta, el instalador lo prueba.

**Copia en la hoja de datos:** el token.

El instalador comprueba que cada permiso exista, pero no puede distinguir «Edit» de «Read» sin crear algo. Revisa que las cinco filas digan «Edit».

## 2.4 Google Cloud

### Entrar a la consola

1. En la misma ventana del correo del curso, entra a `console.cloud.google.com`.
2. La primera vez, Google pide elegir el país y aceptar las condiciones del servicio. Acéptalas y continúa.

### Crear el proyecto

Usa un proyecto nuevo, solo para este curso. El instalador cambia en el proyecto cosas que afectan a todo lo que haya en él (por ejemplo, borra las imágenes de contenedor antiguas del repositorio de Cloud Run).

1. Arriba, al lado del logo de Google Cloud, abre el selector de proyectos y haz clic en «Proyecto nuevo».
2. En «Nombre del proyecto» escribe `ABC123 motor`.
3. Debajo del nombre aparece el ID del proyecto. Haz clic en «Editar» si quieres elegirlo, por ejemplo `abc123-motor`. El ID tiene de 6 a 30 caracteres (minúsculas, números y guiones) y empieza con una letra. Si ya está en uso por otra persona, Google lo avisa: elige otro.
4. En «Ubicación» debería decir «Sin organización». Si aparece el dominio de una universidad, el proyecto queda sujeto a sus políticas; lee antes el aviso «No verificado» de la página 3, sección 3.5, en «El motor en Google Cloud».
5. Haz clic en «Crear».

**Copia en la hoja de datos:** el ID del proyecto (no el nombre).

### Activar la facturación

1. Entra a `console.cloud.google.com/billing/linkedaccount?project=abc123-motor`, con el ID de tu proyecto al final. También se llega desde el menú ☰, «Facturación», con el proyecto elegido arriba.
2. Si la cuenta todavía no tiene una cuenta de facturación, crea una: Google pide el país, los datos de facturación y la tarjeta.
3. Vincula el proyecto a esa cuenta de facturación.
4. Comprueba que la página de Facturación del proyecto muestre la cuenta de facturación vinculada.

Si Google ofrece una prueba gratuita con crédito por tiempo limitado, al terminar la prueba hay que activar la cuenta completa (pasarla a cuenta pagada). Google detiene los recursos de las cuentas que no lo hacen, y con ellos el motor. Mientras el uso siga dentro de la capa gratuita, la cuenta pagada no cobra.

### Crear una alerta de presupuesto

1. En el menú ☰, abre «Facturación» y luego «Presupuestos y alertas».
2. Haz clic en «Crear presupuesto».
3. Ponle un nombre (`ABC123`) y deja como alcance el proyecto del curso.
4. En el importe, elige un monto fijo bajo, por ejemplo 1.000 CLP o 1 dólar (IN5162 usa 1.000 CLP).
5. Deja los umbrales que propone Google y haz clic en «Finalizar».

La alerta manda un correo a la cuenta cuando el gasto se acerca al monto. No detiene el gasto.

## Antes de pasar a la página 3

Revisa que la hoja de datos tenga los 11 datos de la página 1: código, nombre del curso, profesor, correo, contraseña de aplicación, clave de OpenAI, Account ID, token de Cloudflare, ID del proyecto, región (se deja `us-central1`) y correos del equipo. Revisa también que R2 y Zero Trust estén activados en Cloudflare y que el proyecto de Google Cloud tenga la facturación vinculada: el instalador lo comprueba y se detiene si falta.
