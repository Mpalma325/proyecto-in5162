// Configura Cloudflare Access para el sitio, con la API de Cloudflare.
//
//   node scripts/acceso.mjs correo1@uchile.cl correo2@uchile.cl ...
//   node scripts/acceso.mjs --config wrangler.in3401.toml correo1@uchile.cl ...
//
// Lee CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID y WEB_URL del .env de la raíz;
// si vienen como variables de entorno, esas ganan (así lo llama instalar.py).
// El token necesita "Access: Apps and Policies: Edit" y "Access: Organizations,
// Identity Providers, and Groups: Edit". Se puede correr de nuevo: actualiza lo
// que ya existe en vez de duplicarlo. Con otra lista de correos, la reemplaza.
//
// --config es el wrangler.toml del sitio, relativo a web/ (por defecto
// wrangler.toml, el de IN5162). De ahí sale CURSO, que da nombre a las
// aplicaciones: así dos cursos en la misma cuenta no se pisan.
//
// Deja tres cosas:
//   1. La aplicación del sitio: solo entran los correos de la lista, con un
//      código que llega al correo (no hace falta cuenta en ningún lado).
//   2. Una excepción (Bypass) para /api/motor y /api/subir: el motor no puede
//      iniciar sesión en Access, y esas rutas ya exigen TOKEN_MOTOR.
//   3. ACCESO_EQUIPO y ACCESO_AUD en ese wrangler.toml, que el Worker usa para
//      verificar la firma de Access. Después hay que publicar el sitio.

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ENV = resolve(WEB, "..", ".env");

const argumentos = process.argv.slice(2);
const iConfig = argumentos.indexOf("--config");
const archivoConfig = iConfig >= 0 ? argumentos.splice(iConfig, 2)[1] : "wrangler.toml";
if (!archivoConfig || archivoConfig.startsWith("-")) throw new Error("--config necesita el nombre del archivo.");
const WRANGLER = resolve(WEB, archivoConfig);
if (!existsSync(WRANGLER)) throw new Error(`No existe ${WRANGLER}.`);

const env = existsSync(ENV) ? Object.fromEntries(readFileSync(ENV, "utf8").split(/\r?\n/)
  .map((l) => l.match(/^\s*([A-Z_]+)\s*=\s*(.*)$/)).filter(Boolean)
  .map(([, k, v]) => [k, v.trim().replace(/^["']|["']$/g, "")])) : {};
for (const k of ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "WEB_URL"]) {
  if (process.env[k]) env[k] = process.env[k];
}
const TOKEN = env.CLOUDFLARE_API_TOKEN;
if (!TOKEN) throw new Error("Falta CLOUDFLARE_API_TOKEN en el .env de la raíz.");
// Sin valor por defecto: con uno, un curso nuevo configuraba Access sobre el sitio de otro.
if (!env.WEB_URL) throw new Error("Falta WEB_URL (la dirección del sitio) en el .env de la raíz.");

const correos = argumentos.map((c) => c.trim().toLowerCase()).filter(Boolean);
if (!correos.length || correos.some((c) => !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(c))) {
  throw new Error("Uso: node scripts/acceso.mjs [--config wrangler.x.toml] correo1@uchile.cl correo2@uchile.cl ...");
}

let toml = readFileSync(WRANGLER, "utf8");
const CURSO = (toml.match(/^CURSO = "(.+)"$/m) || [])[1]?.toUpperCase();
if (!CURSO) throw new Error(`${archivoConfig} no tiene CURSO en [vars].`);
const SITIO = new URL(env.WEB_URL).host;
const NOMBRE = `${CURSO} sitio`;
const EXCEPCIONES = [[`${CURSO} motor`, `${SITIO}/api/motor`], [`${CURSO} subir`, `${SITIO}/api/subir`]];

async function cf(metodo, ruta, cuerpo) {
  const r = await fetch(`https://api.cloudflare.com/client/v4${ruta}`, {
    method: metodo,
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  const j = await r.json();
  if (!j.success) throw new Error(`${metodo} ${ruta}: ${JSON.stringify(j.errors)}`);
  return j.result;
}

// La cuenta de Cloudflare (sale en `npx wrangler whoami`). Si el .env no la
// dice, se usa la única cuenta a la que alcanza el token; nunca una fija.
async function cuentaDelToken() {
  if (env.CLOUDFLARE_ACCOUNT_ID) return env.CLOUDFLARE_ACCOUNT_ID;
  const cuentas = await cf("GET", "/accounts");
  if (cuentas.length !== 1) {
    throw new Error(`El token alcanza a ${cuentas.length} cuentas: pon la del curso en el .env, `
      + "CLOUDFLARE_ACCOUNT_ID=<id> (sale en `npx wrangler whoami`).");
  }
  console.log(`Cuenta de Cloudflare: ${cuentas[0].name} (${cuentas[0].id}). Para fijarla: CLOUDFLARE_ACCOUNT_ID en el .env.`);
  return cuentas[0].id;
}
const cuenta = await cuentaDelToken();
const base = `/accounts/${cuenta}/access`;

// El equipo de Zero Trust tiene que existir: se crea al activar Zero Trust en el panel.
const organizacion = await cf("GET", `${base}/organizations`).catch(() => null);
if (!organizacion?.auth_domain) {
  throw new Error("Zero Trust no está activado en esta cuenta. Actívalo en one.dash.cloudflare.com (plan Free).");
}
const equipo = organizacion.auth_domain;
console.log(`Equipo de Access: ${equipo}`);

// Entrar con un código al correo: no depende de Google ni de la universidad.
const proveedores = await cf("GET", `${base}/identity_providers`);
if (!proveedores.some((p) => p.type === "onetimepin")) {
  await cf("POST", `${base}/identity_providers`, { name: "Código al correo", type: "onetimepin", config: {} });
  console.log("Agregado el inicio de sesión con código al correo.");
}

const apps = await cf("GET", `${base}/apps`);

/** Crea o actualiza una aplicación y deja una sola política, la que se pasa. */
async function aplicacion(nombre, dominio, politica) {
  const cuerpo = {
    name: nombre, domain: dominio, type: "self_hosted", session_duration: "24h",
    app_launcher_visible: false,
    // La cookie de sesión no viaja en pedidos que otra página arme contra este
    // sitio (CSRF). El Worker además exige que las escrituras vengan de acá.
    same_site_cookie_attribute: "lax", http_only_cookie_attribute: true,
  };
  const ya = apps.find((a) => a.name === nombre || a.domain === dominio);
  const app = ya ? await cf("PUT", `${base}/apps/${ya.id}`, { ...cuerpo, id: ya.id })
    : await cf("POST", `${base}/apps`, cuerpo);
  for (const p of await cf("GET", `${base}/apps/${app.id}/policies`)) {
    await cf("DELETE", `${base}/apps/${app.id}/policies/${p.id}`);
  }
  await cf("POST", `${base}/apps/${app.id}/policies`, { ...politica, precedence: 1 });
  console.log(`${ya ? "Actualizada" : "Creada"}: ${nombre} (${dominio})`);
  return app;
}

const sitio = await aplicacion(NOMBRE, SITIO, {
  name: "Equipo docente", decision: "allow",
  include: correos.map((email) => ({ email: { email } })),
});
for (const [nombre, dominio] of EXCEPCIONES) {
  await aplicacion(nombre, dominio, { name: "Motor (usa TOKEN_MOTOR)", decision: "bypass", include: [{ everyone: {} }] });
}

// El Worker verifica la firma con estos dos datos.
toml = toml.replace(/^ACCESO_EQUIPO = ".*"$/m, `ACCESO_EQUIPO = "${equipo}"`)
  .replace(/^ACCESO_AUD = ".*"$/m, `ACCESO_AUD = "${sitio.aud}"`);
writeFileSync(WRANGLER, toml);

console.log(`\nPueden entrar: ${correos.join(", ")}`);
console.log(`${archivoConfig} actualizado. Falta publicar el sitio.`);
