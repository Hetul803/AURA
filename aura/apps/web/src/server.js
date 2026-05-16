import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { AlphaStore } from './alphaStore.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '../../..');

export const defaultReleasesPath = path.join(repoRoot, 'infra/releases/releases.json');
export const defaultDownloadsPath = path.join(repoRoot, 'infra/releases/downloads.json');
export const defaultAlphaStorePath = process.env.AURA_WEB_DB_PATH || path.join(repoRoot, 'var/private-alpha-store.json');

const brand = {
  name: 'AURA',
  company: 'AURA Labs',
  tagline: 'Your private AI operating identity.',
  support: 'founder@yourcompany.com',
};

export function readJson(filePath, fallback) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  } catch {
    return fallback;
  }
}

export function incrementDownload(os, downloadsPath = defaultDownloadsPath) {
  const data = readJson(downloadsPath, { mac: 0, windows: 0, linux: 0 });
  data[os] = (data[os] || 0) + 1;
  fs.writeFileSync(downloadsPath, JSON.stringify(data, null, 2));
  return data;
}

function json(res, status, payload) {
  res.statusCode = status;
  res.setHeader('content-type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(payload));
}

function html(res, body, status = 200) {
  res.statusCode = status;
  res.setHeader('content-type', 'text/html; charset=utf-8');
  res.end(body);
}

function asset(res, content, type) {
  res.statusCode = 200;
  res.setHeader('content-type', type);
  res.setHeader('cache-control', 'public, max-age=3600');
  res.end(content);
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString('utf-8');
  try {
    return JSON.parse(raw || '{}');
  } catch {
    return {};
  }
}

async function readRawBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf-8');
}

function b64url(buffer) {
  return Buffer.from(buffer).toString('base64url');
}

function parseB64UrlJson(value) {
  return JSON.parse(Buffer.from(value, 'base64url').toString('utf-8'));
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(',')}]`;
  }
  if (value && typeof value === 'object') {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

export function issueLicenseToken({ email, tier = 'private_alpha', expires_at } = {}) {
  const privateKey = process.env.AURA_VENDOR_PRIVATE_KEY;
  if (!privateKey) {
    return {
      ok: false,
      status: 'vendor_private_key_missing',
      message: 'Set AURA_VENDOR_PRIVATE_KEY on the website server to issue signed licenses. Never put this key in the desktop app.',
    };
  }
  if (!email || !String(email).includes('@')) {
    return { ok: false, status: 'email_required', message: 'A valid email is required.' };
  }
  const payload = {
    license_id: `lic_${crypto.randomUUID().replace(/-/g, '')}`,
    account_email: String(email).trim().toLowerCase(),
    tier,
    seats: 1,
    issuer: brand.company,
    features: {
      helper: true,
      guardian: true,
      encrypted_memory: true,
      cryptographic_identity: true,
      overlay: true,
    },
    issued_at: new Date().toISOString(),
  };
  if (expires_at) payload.expires_at = expires_at;
  const body = Buffer.from(stableStringify(payload));
  const signature = crypto.sign(null, body, privateKey);
  return { ok: true, token: `${b64url(body)}.${b64url(signature)}`, payload };
}

function vendorPublicKey() {
  if (process.env.AURA_VENDOR_PUBLIC_KEY) return process.env.AURA_VENDOR_PUBLIC_KEY;
  if (!process.env.AURA_VENDOR_PRIVATE_KEY) return '';
  try {
    return crypto.createPublicKey(process.env.AURA_VENDOR_PRIVATE_KEY).export({ type: 'spki', format: 'pem' }).toString();
  } catch {
    return '';
  }
}

export function verifyLicenseTokenForServer(token) {
  const publicKey = vendorPublicKey();
  if (!publicKey) return { ok: false, status: 'vendor_public_key_missing', message: 'Set AURA_VENDOR_PUBLIC_KEY or AURA_VENDOR_PRIVATE_KEY on the license server.' };
  const parts = String(token || '').split('.');
  if (parts.length !== 2) return { ok: false, status: 'invalid_token_format', message: 'License token must be payload.signature.' };
  const body = Buffer.from(parts[0], 'base64url');
  const signature = Buffer.from(parts[1], 'base64url');
  const verified = crypto.verify(null, body, publicKey, signature);
  if (!verified) return { ok: false, status: 'invalid_signature', message: 'License signature did not verify.' };
  const payload = JSON.parse(body.toString('utf-8'));
  if (payload.expires_at && Date.parse(payload.expires_at) < Date.now()) {
    return { ok: false, status: 'expired', message: 'License expired.', payload };
  }
  return { ok: true, payload };
}

function formEncode(value, prefix = '') {
  const pairs = [];
  for (const [key, item] of Object.entries(value)) {
    const name = prefix ? `${prefix}[${key}]` : key;
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      pairs.push(...formEncode(item, name));
    } else if (Array.isArray(item)) {
      item.forEach((child, index) => pairs.push(...formEncode(child, `${name}[${index}]`)));
    } else if (item !== undefined && item !== null) {
      pairs.push([name, String(item)]);
    }
  }
  return pairs;
}

async function createStripeCheckoutSession({ email, plan = 'alpha' } = {}) {
  const secret = process.env.STRIPE_SECRET_KEY;
  const price = process.env.STRIPE_PRICE_ID || process.env.STRIPE_ALPHA_PRICE_ID;
  const baseUrl = (process.env.PUBLIC_BASE_URL || process.env.AURA_PUBLIC_BASE_URL || 'http://localhost:3000').replace(/\/$/, '');
  if (!secret || !price) {
    return {
      ok: false,
      status: 'stripe_not_configured',
      message: 'Set STRIPE_SECRET_KEY, STRIPE_PRICE_ID, and PUBLIC_BASE_URL to create real checkout sessions.',
      missing: ['STRIPE_SECRET_KEY', 'STRIPE_PRICE_ID'].filter((key) => !process.env[key]),
    };
  }
  const body = new URLSearchParams(formEncode({
    mode: 'subscription',
    customer_email: email,
    client_reference_id: email,
    success_url: `${baseUrl}/downloads?checkout=success&session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${baseUrl}/downloads?checkout=cancelled`,
    allow_promotion_codes: true,
    line_items: [{ price, quantity: 1 }],
    metadata: { product: brand.name, plan, email },
    subscription_data: { metadata: { product: brand.name, plan, email } },
  }));
  const res = await fetch('https://api.stripe.com/v1/checkout/sessions', {
    method: 'POST',
    headers: {
      authorization: `Basic ${Buffer.from(`${secret}:`).toString('base64')}`,
      'content-type': 'application/x-www-form-urlencoded',
    },
    body,
  });
  const payload = await res.json();
  if (!res.ok) return { ok: false, status: 'stripe_error', message: payload?.error?.message || 'Stripe checkout creation failed.', stripe: payload };
  return { ok: true, session: payload, url: payload.url };
}

function verifyStripeSignature(rawBody, signatureHeader, secret) {
  if (!secret) return { ok: false, status: 'stripe_webhook_secret_missing' };
  const pieces = Object.fromEntries(String(signatureHeader || '').split(',').map((part) => part.split('=')));
  const timestamp = pieces.t;
  const signature = pieces.v1;
  if (!timestamp || !signature) return { ok: false, status: 'stripe_signature_missing' };
  const expected = crypto.createHmac('sha256', secret).update(`${timestamp}.${rawBody}`).digest('hex');
  if (signature.length !== expected.length) return { ok: false, status: 'stripe_signature_invalid' };
  const valid = crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
  return valid ? { ok: true } : { ok: false, status: 'stripe_signature_invalid' };
}

function sanitizeCrashReport(report) {
  const text = JSON.stringify(report || {});
  const redacted = text
    .replace(/sk_(live|test)_[A-Za-z0-9_]+/g, '[redacted_stripe_key]')
    .replace(/(password|api[_-]?key|token|secret)["':=\s]+[^"',\s}]+/gi, '$1=[redacted]');
  return JSON.parse(redacted);
}

const styles = `
:root{color-scheme:dark;--bg:#030712;--panel:rgba(8,18,34,.72);--line:rgba(137,231,255,.18);--text:#f3fbff;--muted:#9db7c9;--cyan:#70f4ff;--green:#79f7c3;--gold:#ffe08a;--red:#ff6682}
*{box-sizing:border-box}body{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(circle at 48% 0%,rgba(95,228,255,.22),transparent 36%),radial-gradient(circle at 78% 18%,rgba(121,247,195,.12),transparent 28%),linear-gradient(180deg,#030712,#06111d 52%,#02050b);color:var(--text);overflow-x:hidden}a{color:inherit;text-decoration:none}input{border:1px solid var(--line);background:rgba(3,9,18,.72);color:var(--text);border-radius:14px;padding:13px 14px;min-width:260px}button,.button{border:1px solid var(--line);background:rgba(112,244,255,.12);color:var(--text);border-radius:14px;padding:13px 18px;font-weight:800;cursor:pointer;display:inline-flex;gap:9px;align-items:center;justify-content:center}.button.primary,button.primary{background:linear-gradient(135deg,#70f4ff,#79f7c3);color:#031018;box-shadow:0 0 34px rgba(112,244,255,.26)}.button.disabled{opacity:.55;cursor:not-allowed;background:rgba(255,255,255,.06)}nav{position:sticky;top:0;z-index:10;backdrop-filter:blur(22px);background:rgba(3,7,18,.72);border-bottom:1px solid var(--line)}.nav-inner{max-width:1180px;margin:auto;padding:16px 22px;display:flex;align-items:center;justify-content:space-between;gap:18px}.brand{display:flex;align-items:center;gap:12px;font-weight:950}.mark{width:36px;height:36px;border-radius:50%;background:radial-gradient(circle,#fff 0 8%,#70f4ff 14%,rgba(112,244,255,.12) 55%,transparent 70%);box-shadow:0 0 26px rgba(112,244,255,.52)}.nav-links{display:flex;gap:18px;color:var(--muted);font-size:14px}.hero{min-height:calc(100vh - 68px);max-width:1180px;margin:auto;padding:70px 22px 34px;display:grid;grid-template-columns:minmax(0,1.05fr) minmax(360px,.95fr);gap:54px;align-items:center}.eyebrow{color:var(--green);text-transform:uppercase;font-size:12px;font-weight:950;letter-spacing:.08em}.hero h1{font-size:clamp(48px,7vw,92px);line-height:.93;margin:14px 0 22px;letter-spacing:0}.lead{font-size:clamp(18px,2.2vw,24px);color:#cfe6f2;line-height:1.48;max-width:720px}.hero-actions,.checkout-form{display:flex;flex-wrap:wrap;gap:12px;margin:30px 0}.checkout-form{margin:20px 0 8px}.form-status{color:var(--gold);min-height:24px}.trust-row{display:flex;flex-wrap:wrap;gap:10px;color:#b9d2df}.trust-row span{border:1px solid var(--line);border-radius:999px;padding:9px 12px;background:rgba(255,255,255,.045)}.presence{position:relative;min-height:560px;border:1px solid var(--line);border-radius:34px;background:linear-gradient(145deg,rgba(9,20,38,.72),rgba(4,9,20,.88));box-shadow:0 34px 120px rgba(0,0,0,.46),inset 0 0 80px rgba(112,244,255,.04);overflow:hidden}.presence:before{content:"";position:absolute;inset:-40%;background:conic-gradient(from 180deg,transparent,rgba(112,244,255,.18),transparent,rgba(121,247,195,.16),transparent);animation:spin 18s linear infinite}.orb{position:absolute;inset:70px;display:grid;place-items:center}.core{width:245px;height:245px;border-radius:50%;background:radial-gradient(circle,#fff 0 5%,#83f7ff 9%,rgba(112,244,255,.18) 34%,rgba(7,17,30,.88) 63%,transparent 71%);box-shadow:0 0 70px rgba(112,244,255,.54),inset 0 0 34px rgba(255,255,255,.22);animation:breathe 3.4s ease-in-out infinite}.ring{position:absolute;border:1px solid rgba(112,244,255,.28);border-radius:50%;animation:pulse 4s ease-in-out infinite}.r1{width:330px;height:330px}.r2{width:430px;height:430px;animation-delay:.8s}.r3{width:520px;height:520px;animation-delay:1.6s}.status-card{position:absolute;left:26px;right:26px;bottom:26px;padding:22px;border:1px solid var(--line);border-radius:22px;background:rgba(3,9,18,.82);backdrop-filter:blur(18px)}.status-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:16px}.status-grid div,.tile{border:1px solid rgba(255,255,255,.1);border-radius:16px;padding:14px;background:rgba(255,255,255,.045)}.status-grid span,.tile span{display:block;color:var(--muted);font-size:12px}.status-grid strong,.tile strong{display:block;margin-top:6px}.section{max-width:1180px;margin:auto;padding:82px 22px}.section h2{font-size:clamp(34px,4.5vw,58px);line-height:1.02;margin:10px 0 18px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.card{border:1px solid var(--line);border-radius:22px;background:var(--panel);padding:22px;min-height:220px;box-shadow:inset 0 0 48px rgba(112,244,255,.035)}.card h3{font-size:22px;margin:10px 0}.card p{color:#bfd4e2;line-height:1.55}.flow{display:grid;grid-template-columns:1fr 1fr;gap:18px}.dialogue{display:grid;gap:12px}.turn{padding:16px 18px;border-radius:20px;border:1px solid var(--line);background:rgba(255,255,255,.045)}.turn span{color:var(--green);font-size:12px;text-transform:uppercase;font-weight:900}.guardian span{color:var(--gold)}.download{display:grid;grid-template-columns:1.2fr .8fr;gap:18px;align-items:stretch}.download-panel{border:1px solid rgba(121,247,195,.28);border-radius:28px;padding:28px;background:linear-gradient(145deg,rgba(13,34,44,.82),rgba(4,12,20,.88));box-shadow:0 0 56px rgba(121,247,195,.12)}.download-options{display:grid;gap:12px}.legal-page{max-width:880px;margin:auto;padding:80px 22px;color:#d6e8f0}.legal-page h1{font-size:48px}.legal-page p,.legal-page li{color:#bfd4e2;line-height:1.7}footer{border-top:1px solid var(--line);padding:30px 22px;color:var(--muted)}.footer-inner{max-width:1180px;margin:auto;display:flex;gap:16px;justify-content:space-between;flex-wrap:wrap}@keyframes spin{to{transform:rotate(360deg)}}@keyframes breathe{0%,100%{transform:scale(.96);filter:hue-rotate(0)}50%{transform:scale(1.04);filter:hue-rotate(18deg)}}@keyframes pulse{0%,100%{transform:scale(.94);opacity:.45}50%{transform:scale(1.04);opacity:1}}@media(max-width:900px){.hero,.flow,.download{grid-template-columns:1fr}.grid{grid-template-columns:1fr 1fr}.presence{min-height:460px}.nav-links{display:none}}@media(max-width:560px){.grid{grid-template-columns:1fr}.hero{padding-top:42px}.status-grid{grid-template-columns:1fr}.core{width:180px;height:180px}.r1{width:240px;height:240px}.r2{width:300px;height:300px}.r3{width:360px;height:360px}}
`;

function shell(content, title = `${brand.name} — ${brand.tagline}`) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><title>${title}</title><meta name="description" content="${brand.name} is a private AI operating identity with Helper, Guardian, Memory, and cryptographic Identity layers."/><link rel="stylesheet" href="/assets/site.css"/></head><body><nav><div class="nav-inner"><a class="brand" href="/"><span class="mark"></span><span>${brand.name}</span></a><div class="nav-links"><a href="#product">Product</a><a href="#guardian">Guardian</a><a href="#memory">Memory</a><a href="#download">Download</a><a href="/privacy">Privacy</a></div></div></nav>${content}<footer><div class="footer-inner"><span>${brand.company} — private AI operating identity</span><span><a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> · <a href="/security">Security</a></span></div></footer><script src="/assets/site.js"></script></body></html>`;
}

function landingPage(releases = {}) {
  const macUrl = releases?.downloads?.mac || '/api/download?os=mac';
  return shell(`
    <main class="hero">
      <section>
        <div class="eyebrow">Private AI operating identity</div>
        <h1>Not a chatbot. Your AI layer over the computer.</h1>
        <p class="lead">${brand.name} helps you act, protects you through Guardian, remembers your work locally, and represents you through a cryptographic identity you own.</p>
        <div class="hero-actions"><a class="button primary" href="${macUrl}" data-download="mac">Download Mac private alpha</a><a class="button" href="#download">See compatibility</a></div>
        <div class="trust-row"><span>Local-first</span><span>Encrypted memory</span><span>Guardian approvals</span><span>Signed identity</span><span>Bring your own models</span></div>
      </section>
      <section class="presence" aria-label="${brand.name} presence preview">
        <div class="orb"><span class="ring r1"></span><span class="ring r2"></span><span class="ring r3"></span><div class="core"></div></div>
        <div class="status-card"><div class="eyebrow">${brand.name} is online</div><strong>User: “Clone this repo.”</strong><div class="status-grid"><div><span>${brand.name} sees</span><strong>GitHub repo</strong></div><div><span>Guardian</span><strong>Approval required</strong></div><div><span>Memory</span><strong>Using workspace preference</strong></div><div><span>Identity</span><strong>Personal, signed</strong></div></div></div>
      </section>
    </main>
    <section id="product" class="section">
      <div class="eyebrow">The four layers</div><h2>The assistant users can trust with their computer.</h2>
      <div class="grid">
        <article class="card"><span class="eyebrow">Helper</span><h3>Tell it intent.</h3><p>${brand.name} can clone repos, draft replies, create coding jobs, prepare prompts for ChatGPT/Claude, and automate workflows with approval.</p></article>
        <article class="card"><span class="eyebrow">Guardian</span><h3>The intent firewall.</h3><p>Dangerous commands, paste/send, memory export/import, secrets, file writes, workflow replay, and model spend are watched and approval-gated.</p></article>
        <article class="card"><span class="eyebrow">Memory</span><h3>Private from day one.</h3><p>Preferences, workflows, safety decisions, identity context, and repeated patterns are encrypted locally and owned by the user.</p></article>
        <article class="card"><span class="eyebrow">Identity</span><h3>Acts as you.</h3><p>Personal, Work, Company, and Session identities are scoped separately and backed by local cryptographic keys.</p></article>
      </div>
    </section>
    <section id="guardian" class="section flow">
      <div><div class="eyebrow">Core loop</div><h2>${brand.name} does the work. Guardian protects the boundary.</h2><p class="lead">Every useful action flows through context, risk classification, approval, audit, memory, and signed identity.</p></div>
      <div class="dialogue"><div class="turn"><span>User</span><p>Clone this repo.</p></div><div class="turn"><span>${brand.name}</span><p>I’m checking what you’re looking at. I found Hetul803/AURA.</p></div><div class="turn guardian"><span>Guardian</span><p>I need approval before running git clone in your workspace.</p></div><div class="turn"><span>${brand.name}</span><p>Done. I cloned it and recorded the action under Personal identity.</p></div></div>
    </section>
    <section id="memory" class="section">
      <div class="eyebrow">Why users stay</div><h2>Memory becomes the moat.</h2>
      <div class="grid"><article class="card"><h3>Remembers preferences</h3><p>Writing style, workspace folders, trusted apps, repeated tasks, and safe choices.</p></article><article class="card"><h3>Rejects secrets</h3><p>Passwords, API keys, private keys, card-like strings, and risky memory writes are blocked.</p></article><article class="card"><h3>Survives models</h3><p>Memory belongs to the user, not one model provider.</p></article><article class="card"><h3>Boundary aware</h3><p>Personal, Work, Company, and Session memories stay scoped unless explicitly approved.</p></article></div>
    </section>
    <section id="download" class="section download">
      <div class="download-panel"><div class="eyebrow">Private alpha</div><h2>Download ${brand.name} for Mac.</h2><p class="lead">For Apple Silicon Macs. This private-alpha build is local-first, unsigned until notarization, and designed for hands-on founder testing.</p><form class="checkout-form" id="checkout-form"><input name="email" type="email" placeholder="founder@example.com" aria-label="email for checkout"/><button class="primary" type="submit">Start private-alpha checkout</button></form><div class="form-status" id="checkout-status"></div><div class="hero-actions"><a class="button primary" href="${macUrl}" data-download="mac">Download Mac DMG</a><a class="button" href="/security">Read security model</a></div></div>
      <div class="download-options"><div class="tile"><span>macOS</span><strong>Available private alpha</strong></div><div class="tile"><span>Windows</span><strong>Coming soon</strong></div><div class="tile"><span>Linux</span><strong>Coming later</strong></div><div class="tile"><span>Voice</span><strong>Native Mac speech now; production STT next</strong></div></div>
    </section>
  `);
}

function legalPage(kind) {
  const title = kind === 'privacy' ? 'Privacy Policy' : kind === 'terms' ? 'Terms of Use' : 'Security Model';
  const body = kind === 'privacy'
    ? `<p>${brand.name} is local-first. Profile data, encrypted memory, identity keys, and workflow history are stored on the user's device unless the user explicitly exports or enables future sync.</p><ul><li>Memory values are encrypted at rest.</li><li>Secrets are rejected before memory storage.</li><li>Risky actions require approval.</li><li>Cloud model use is optional and user-controlled.</li></ul>`
    : kind === 'terms'
    ? `<p>This private-alpha software is experimental. Users must review approvals before allowing ${brand.name} to control apps, files, browser sessions, terminal commands, or paid tools.</p><ul><li>No unattended destructive automation.</li><li>No resale or redistribution of private alpha builds.</li><li>Licenses may be revoked for abuse.</li></ul>`
    : `<p>Guardian currently protects AURA-managed shell, file, paste/send, memory, workflow, import/export, and model-cost actions. OS-wide website permission and third-party app file-access monitoring are future native extensions, not claimed in this build.</p><ul><li>Ed25519 identity signing.</li><li>Signed license-token verification.</li><li>Encrypted memory values and identity private keys.</li><li>Audit records for significant actions.</li></ul>`;
  return shell(`<main class="legal-page"><div class="eyebrow">${brand.company}</div><h1>${title}</h1>${body}<p>Contact: ${brand.support}</p></main>`, `${title} — ${brand.name}`);
}

function clientScript() {
  return `document.querySelectorAll('[data-download]').forEach(link=>{link.addEventListener('click',async()=>{try{await fetch('/api/download?os='+encodeURIComponent(link.dataset.download||'unknown'))}catch{}})});const f=document.getElementById('checkout-form');const s=document.getElementById('checkout-status');if(f){f.addEventListener('submit',async e=>{e.preventDefault();s.textContent='Creating secure checkout...';const email=new FormData(f).get('email');try{const r=await fetch('/api/checkout/create',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({email})});const j=await r.json();if(j.ok&&j.url){location.href=j.url}else{s.textContent=j.message||'Checkout is not configured yet.'}}catch(err){s.textContent='Checkout failed. Please email support.'}})}`;
}

export function createServer(options = {}) {
  const releasesPath = options.releasesPath || defaultReleasesPath;
  const downloadsPath = options.downloadsPath || defaultDownloadsPath;
  const store = options.store || new AlphaStore(options.storePath || defaultAlphaStorePath);
  return http.createServer(async (req, res) => {
    const url = new URL(req.url || '/', 'http://localhost');
    if (url.pathname === '/assets/site.css') return asset(res, styles, 'text/css; charset=utf-8');
    if (url.pathname === '/assets/site.js') return asset(res, clientScript(), 'application/javascript; charset=utf-8');
    if (url.pathname === '/') return html(res, landingPage(readJson(releasesPath, {})));
    if (url.pathname === '/downloads') return html(res, landingPage(readJson(releasesPath, {})));
    if (url.pathname === '/privacy') return html(res, legalPage('privacy'));
    if (url.pathname === '/terms') return html(res, legalPage('terms'));
    if (url.pathname === '/security') return html(res, legalPage('security'));
    if (url.pathname === '/api/releases') return json(res, 200, readJson(releasesPath, {}));
    if (url.pathname === '/api/download') {
      const os = url.searchParams.get('os') || 'unknown';
      return json(res, 200, incrementDownload(os, downloadsPath));
    }
    if (url.pathname === '/api/license/issue' && req.method === 'POST') {
      const body = await readBody(req);
      const result = issueLicenseToken(body);
      if (result.ok) store.storeLicense(result.payload, result.token, { source: 'manual_issue_api' });
      return json(res, result.ok ? 200 : 400, result);
    }
    if (url.pathname === '/api/checkout/create' && req.method === 'POST') {
      const body = await readBody(req);
      const email = String(body.email || '').trim().toLowerCase();
      if (!email.includes('@')) return json(res, 400, { ok: false, status: 'email_required', message: 'Enter an email address before checkout.' });
      store.upsertAccount(email, { plan: body.plan || 'alpha', source: 'checkout' });
      const result = await createStripeCheckoutSession({ email, plan: body.plan || 'alpha' });
      if (result.ok) store.storeCheckoutSession({ id: result.session.id, email, plan: body.plan || 'alpha', stripe: result.session, status: 'open' });
      return json(res, result.ok ? 200 : 400, result);
    }
    if (url.pathname === '/api/stripe/webhook' && req.method === 'POST') {
      const raw = await readRawBody(req);
      const signature = req.headers['stripe-signature'];
      const verified = verifyStripeSignature(raw, signature, process.env.STRIPE_WEBHOOK_SECRET);
      if (!verified.ok) return json(res, 400, verified);
      const event = JSON.parse(raw);
      if (event.type === 'checkout.session.completed') {
        const session = event.data?.object || {};
        const email = String(session.customer_details?.email || session.customer_email || session.metadata?.email || '').trim().toLowerCase();
        if (email) {
          store.upsertAccount(email, { stripe_customer_id: session.customer, subscription_id: session.subscription, billing_status: 'active' });
          const issued = issueLicenseToken({ email, tier: session.metadata?.plan || 'private_alpha' });
          if (issued.ok) store.storeLicense(issued.payload, issued.token, { source: 'stripe_webhook', stripe_session_id: session.id, stripe_customer_id: session.customer, subscription_id: session.subscription });
          store.storeCheckoutSession({ id: session.id, email, stripe: session, status: 'complete', license_id: issued.payload?.license_id });
        }
      }
      return json(res, 200, { received: true });
    }
    if (url.pathname === '/api/devices/activate' && req.method === 'POST') {
      const body = await readBody(req);
      if (!body.device_fingerprint) return json(res, 400, { ok: false, status: 'device_fingerprint_required', message: 'Device fingerprint is required for activation.' });
      const verified = verifyLicenseTokenForServer(body.token);
      if (!verified.ok) return json(res, 400, verified);
      const stored = store.storeLicense(verified.payload, body.token, { source: 'device_activation' });
      const activation = store.activateDevice(stored, {
        device_fingerprint: body.device_fingerprint,
        device_name: body.device_name,
        metadata: body.metadata,
      });
      return json(res, activation.ok ? 200 : 409, activation);
    }
    if (url.pathname === '/api/devices/revoke' && req.method === 'POST') {
      const expected = process.env.AURA_ADMIN_TOKEN;
      if (expected && req.headers.authorization !== `Bearer ${expected}`) return json(res, 401, { ok: false, status: 'unauthorized' });
      const body = await readBody(req);
      return json(res, 200, store.revokeActivation(body.activation_id, body.reason || 'manual'));
    }
    if (url.pathname.startsWith('/api/licenses/') && req.method === 'GET') {
      const licenseId = decodeURIComponent(url.pathname.split('/').pop() || '');
      const license = store.getLicense(licenseId);
      if (!license) return json(res, 404, { ok: false, status: 'not_found' });
      return json(res, 200, { ok: true, license: { ...license, token: undefined }, activations: store.activeActivationsForLicense(licenseId) });
    }
    if (url.pathname === '/api/crash-reports' && req.method === 'POST') {
      const report = sanitizeCrashReport(await readBody(req));
      return json(res, 200, { ok: true, report: store.recordCrash(report) });
    }
    if (url.pathname === '/api/update/latest') {
      const releases = readJson(releasesPath, {});
      return json(res, 200, {
        ok: true,
        version: releases.version || '1.0.0',
        platform: url.searchParams.get('platform') || 'darwin',
        arch: url.searchParams.get('arch') || 'arm64',
        download: releases?.downloads?.mac || null,
        notes: releases.notes || 'Private alpha release.',
      });
    }
    html(res, shell(`<main class="legal-page"><h1>Not found</h1><p>That page does not exist.</p></main>`, `Not found — ${brand.name}`), 404);
  });
}

const server = createServer();

if (process.env.NODE_ENV !== 'test') {
  const port = Number(process.env.PORT || 3000);
  server.listen(port, () => console.log(`${brand.name} website on http://localhost:${port}`));
}

export default server;
