// Configura Cloudflare Access para el sitio, con la API de Cloudflare.
//
//   node scripts/acceso.mjs correo1@uchile.cl correo2@uchile.cl ...
//
// Necesita CLOUDFLARE_API_TOKEN en el .env de la raíz, con los permisos
// "Access: Apps and Policies: Edit" y "Access: Organizations, Identity
// Providers, and Groups: Edit". Se puede correr de nuevo: actualiza lo que ya
// existe en vez de duplicarlo. Con otra lista de correos, la reemplaza.
//
// Deja tres cosas:
//   1. La aplicación del sitio: solo entran los correos de la lista, con un
//      código que llega al correo (no hace falta cuenta en ningún lado).
//   2. Una excepción (Bypass) para /api/motor y /api/subir: el motor no puede
//      iniciar sesión en Access, y esas rutas ya exigen TOKEN_MOTOR.
//   3. ACCESO_EQUIPO y ACCESO_AUD en wrangler.toml, que el Worker usa para
//      verificar la firma de Access. Después hay que publicar: npm run deploy.

import { readFileSync, writeFileSync } from "node:fs";

const RAIZ = new URL("../../", import.meta.url);
const WRANGLER = new URL("../wrangler.toml", import.meta.url);

const env = Object.fromEntries(readFileSync(new URL(".env", RAIZ), "utf8").split(/\r?\n/)
  .map((l) => l.match(/^\s*([A-Z_]+)\s*=\s*(.*)$/)).filter(Boolean)
  .map(([, k, v]) => [k, v.trim().replace(/^["']|["']$/g, "")]));
const TOKEN = env.CLOUDFLARE_API_TOKEN;
if (!TOKEN) throw new Error("Falta CLOUDFLARE_API_TOKEN en el .env de la raíz.");

const correos = process.argv.slice(2).map((c) => c.trim().toLowerCase()).filter(Boolean);
if (!correos.length || correos.some((c) => !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(c))) {
  throw new Error("Uso: node scripts/acceso.mjs correo1@uchile.cl correo2@uchile.cl ...");
}

const SITIO = new URL(env.WEB_URL || "https://in5162.in5162-web.workers.dev").host;
const NOMBRE = "IN5162 sitio";
const EXCEPCIONES = [["IN5162 motor", `${SITIO}/api/motor`], ["IN5162 subir", `${SITIO}/api/subir`]];

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

// La cuenta de Cloudflare de in5162@uchile.cl (sale en `npx wrangler whoami`).
const cuenta = env.CLOUDFLARE_ACCOUNT_ID || "5b630024b4683ba044bca1ad69f07a3c";
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
let toml = readFileSync(WRANGLER, "utf8");
toml = toml.replace(/^ACCESO_EQUIPO = ".*"$/m, `ACCESO_EQUIPO = "${equipo}"`)
  .replace(/^ACCESO_AUD = ".*"$/m, `ACCESO_AUD = "${sitio.aud}"`);
writeFileSync(WRANGLER, toml);

console.log(`\nPueden entrar: ${correos.join(", ")}`);
console.log("wrangler.toml actualizado. Falta publicar: npm run deploy");
