/**
 * Verificar que una petición pasó de verdad por Cloudflare Access.
 *
 * Access agrega a cada petición que deja pasar un token firmado
 * (Cf-Access-Jwt-Assertion). Acá se comprueba la firma con las claves públicas
 * del equipo de Access, que el token sea para esta aplicación (aud), que no
 * haya vencido y que traiga un correo. Si algo falla, no hay persona.
 *
 * No se usa el encabezado de correo que Access también agrega: Cloudflare lo
 * borra si lo manda un tercero, pero si Access se desactivara por error, lo
 * único que sigue protegiendo al curso es esta firma.
 */

export interface ConfigAcceso {
  /** El dominio del equipo de Zero Trust: "in5162.cloudflareaccess.com". */
  equipo: string;
  /** El "Application Audience (AUD) Tag" de la aplicación de Access. */
  aud: string;
}

type Claves = Map<string, CryptoKey>;
export type ObtenerClaves = (equipo: string, renovar: boolean) => Promise<Claves>;

const ALGORITMO = { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" };

function desdeBase64url(s: string): Uint8Array {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4);
  const bin = atob(b64);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

function jsonBase64url(s: string): Record<string, unknown> {
  return JSON.parse(new TextDecoder().decode(desdeBase64url(s)));
}

// Las claves del equipo cambian rara vez; se guardan una hora por instancia.
let guardadas: { equipo: string; claves: Claves; hasta: number } | null = null;

/** Las claves públicas del equipo, desde /cdn-cgi/access/certs. */
export const clavesDeCloudflare: ObtenerClaves = async (equipo, renovar) => {
  if (!renovar && guardadas && guardadas.equipo === equipo && guardadas.hasta > Date.now()) {
    return guardadas.claves;
  }
  const r = await fetch(`https://${equipo}/cdn-cgi/access/certs`);
  if (!r.ok) throw new Error(`No pude leer las claves de Access: ${r.status}`);
  const { keys } = await r.json<{ keys: (JsonWebKey & { kid: string })[] }>();
  const claves: Claves = new Map();
  for (const k of keys) {
    claves.set(k.kid, await crypto.subtle.importKey("jwk", k, ALGORITMO, false, ["verify"]));
  }
  guardadas = { equipo, claves, hasta: Date.now() + 3600_000 };
  return claves;
};

/**
 * El correo de quien hizo la petición, o null si el token no es válido.
 * `ahora` y `obtenerClaves` se pueden cambiar para probarlo sin red.
 */
export async function correoVerificado(
  token: string | null,
  cfg: ConfigAcceso,
  obtenerClaves: ObtenerClaves = clavesDeCloudflare,
  ahora: number = Date.now() / 1000,
): Promise<string | null> {
  if (!token || !cfg.equipo || !cfg.aud) return null;
  const partes = token.split(".");
  if (partes.length !== 3) return null;
  try {
    const cabecera = jsonBase64url(partes[0]);
    const datos = jsonBase64url(partes[1]);
    if (cabecera.alg !== "RS256" || typeof cabecera.kid !== "string") return null;

    let claves = await obtenerClaves(cfg.equipo, false);
    if (!claves.has(cabecera.kid)) claves = await obtenerClaves(cfg.equipo, true); // rotaron las claves
    const clave = claves.get(cabecera.kid);
    if (!clave) return null;
    const firmado = new TextEncoder().encode(`${partes[0]}.${partes[1]}`);
    if (!(await crypto.subtle.verify(ALGORITMO, clave, desdeBase64url(partes[2]), firmado))) return null;

    const auds = Array.isArray(datos.aud) ? datos.aud : [datos.aud];
    if (!auds.includes(cfg.aud)) return null;
    if (datos.iss !== `https://${cfg.equipo}`) return null;
    if (typeof datos.exp !== "number" || datos.exp < ahora) return null;
    if (typeof datos.nbf === "number" && datos.nbf > ahora + 60) return null;
    // Los tokens de servicio no traen correo: no son personas.
    return typeof datos.email === "string" && datos.email ? datos.email : null;
  } catch {
    return null;
  }
}
