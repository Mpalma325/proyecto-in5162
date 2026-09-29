// Prueba acceso.ts sin red: firma tokens con una clave generada acá y revisa
// que solo el token correcto dé un correo. La corre pruebas/web.py.
import { correoVerificado } from "../src/acceso.ts";

const ALG = { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" };
const par = await crypto.subtle.generateKey({ ...ALG, modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]) }, true, ["sign", "verify"]);
const otro = await crypto.subtle.generateKey({ ...ALG, modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]) }, true, ["sign", "verify"]);
const b64 = (b) => Buffer.from(b).toString("base64url");
const cfg = { equipo: "curso.cloudflareaccess.com", aud: "aud-del-sitio" };
const ahora = 1_800_000_000;

async function firmar(datos, { kid = "k1", clave = par.privateKey, alg = "RS256" } = {}) {
  const c = b64(JSON.stringify({ alg, kid })), d = b64(JSON.stringify(datos));
  const f = await crypto.subtle.sign(ALG, clave, new TextEncoder().encode(`${c}.${d}`));
  return `${c}.${d}.${b64(f)}`;
}
let pedidas = 0;
const claves = async (_e, renovar) => { pedidas++; return new Map(renovar ? [["k1", par.publicKey], ["k2", par.publicKey]] : [["k1", par.publicKey]]); };
const base = { aud: [cfg.aud], iss: `https://${cfg.equipo}`, exp: ahora + 600, iat: ahora, email: "profe@uchile.cl" };
const casos = [
  ["token válido da el correo", await firmar(base), "profe@uchile.cl"],
  ["sin token no hay persona", null, null],
  ["otra aplicación (aud) no sirve", await firmar({ ...base, aud: ["otra"] }), null],
  ["otro equipo (iss) no sirve", await firmar({ ...base, iss: "https://intruso.cloudflareaccess.com" }), null],
  ["token vencido no sirve", await firmar({ ...base, exp: ahora - 1 }), null],
  ["firmado con otra clave no sirve", await firmar(base, { clave: otro.privateKey }), null],
  ["token de servicio (sin correo) no es persona", await firmar({ ...base, email: undefined, common_name: "x" }), null],
  ["alg distinto de RS256 no sirve", await firmar(base, { alg: "HS256" }), null],
  ["basura no rompe nada", "a.b.c", null],
  ["clave rotada: se renuevan las claves", await firmar(base, { kid: "k2" }), "profe@uchile.cl"],
];
let mal = 0;
for (const [nombre, token, esperado] of casos) {
  const r = await correoVerificado(token, cfg, claves, ahora);
  console.log(`${r === esperado ? "OK" : "FALLA"}\t${nombre}${r === esperado ? "" : ` (dio ${r})`}`);
  if (r !== esperado) mal++;
}
const sinConfig = await correoVerificado(await firmar(base), { equipo: "", aud: "" }, claves, ahora);
console.log(`${sinConfig === null ? "OK" : "FALLA"}\tsin ACCESO_EQUIPO/AUD configurados nadie entra`);
process.exit(mal || sinConfig !== null ? 1 : 0);
