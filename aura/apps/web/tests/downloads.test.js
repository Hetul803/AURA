import { afterEach, describe, expect, it } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { AlphaStore } from '../src/alphaStore.js';
import { createServer, incrementDownload, issueLicenseToken } from '../src/server.js';

function tempJson(initial) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'aura-web-test-'));
  const file = path.join(dir, 'downloads.json');
  fs.writeFileSync(file, JSON.stringify(initial, null, 2));
  return { dir, file };
}

function tempStore() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'aura-web-store-test-'));
  return { dir, store: new AlphaStore(path.join(dir, 'store.json')) };
}

function request(server, method, pathname, body) {
  return new Promise((resolve, reject) => {
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      const req = crypto.randomUUID();
      const data = body ? JSON.stringify(body) : '';
      const call = globalThis.fetch(`http://127.0.0.1:${port}${pathname}`, {
        method,
        headers: { 'content-type': 'application/json', 'x-test-request': req },
        body: data || undefined,
        redirect: 'manual',
      });
      call.then(resolve).catch(reject).finally(() => server.close());
    });
  });
}

afterEach(() => {
  delete process.env.AURA_VENDOR_PRIVATE_KEY;
  delete process.env.AURA_LOCAL_MAC_ARTIFACT;
  delete process.env.AURA_DOWNLOAD_MAC_URL;
  delete process.env.STRIPE_SECRET_KEY;
  delete process.env.STRIPE_PRICE_ID;
  delete process.env.STRIPE_WEBHOOK_SECRET;
});

describe('download counter', () => {
  it('increments without mutating repo fixtures', () => {
    const { file } = tempJson({ mac: 1, windows: 0, linux: 0 });
    const after = incrementDownload('mac', file);
    expect(after.mac).toBe(2);
    expect(JSON.parse(fs.readFileSync(file, 'utf-8')).mac).toBe(2);
  });
});

describe('marketing website', () => {
  it('renders the product promise clearly', async () => {
    const downloads = tempJson({ mac: 1, windows: 0, linux: 0 });
    const releases = path.join(downloads.dir, 'releases.json');
    fs.writeFileSync(releases, JSON.stringify({ downloads: { mac: 'https://example.com/aura.dmg' } }));
    const res = await request(createServer({ releasesPath: releases, downloadsPath: downloads.file }), 'GET', '/');
    const html = await res.text();

    expect(res.status).toBe(200);
    expect(html).toContain('Not a chatbot');
    expect(html).toContain('Helper');
    expect(html).toContain('Guardian');
    expect(html).toContain('Memory');
    expect(html).toContain('Identity');
    expect(html).toContain('Download Mac private alpha');
    expect(html).toContain('Windows');
    expect(html).toContain('Coming soon');
  });

  it('does not issue licenses without vendor private key', () => {
    const result = issueLicenseToken({ email: 'alpha@example.com' });
    expect(result.ok).toBe(false);
    expect(result.status).toBe('vendor_private_key_missing');
  });

  it('issues signed private-alpha licenses when vendor key is configured', () => {
    const { privateKey, publicKey } = crypto.generateKeyPairSync('ed25519');
    process.env.AURA_VENDOR_PRIVATE_KEY = privateKey.export({ type: 'pkcs8', format: 'pem' });

    const result = issueLicenseToken({ email: 'Alpha@Example.com' });
    const [body, signature] = result.token.split('.');

    expect(result.ok).toBe(true);
    expect(result.payload.account_email).toBe('alpha@example.com');
    expect(result.payload.features.guardian).toBe(true);
    expect(result.payload.features.cryptographic_identity).toBe(true);
    expect(
      crypto.verify(
        null,
        Buffer.from(body, 'base64url'),
        publicKey,
        Buffer.from(signature, 'base64url'),
      ),
    ).toBe(true);
  });

  it('creates checkout only when Stripe env is configured', async () => {
    const { store } = tempStore();
    const res = await request(createServer({ store }), 'POST', '/api/checkout/create', { email: 'alpha@example.com' });
    const body = await res.json();

    expect(res.status).toBe(400);
    expect(body.status).toBe('stripe_not_configured');
    expect(store.read().accounts['alpha@example.com']).toBeTruthy();
  });

  it('serves a local Mac DMG artifact instead of a JSON counter', async () => {
    const downloads = tempJson({ mac: 0, windows: 0, linux: 0 });
    const artifact = path.join(downloads.dir, 'AURA-test.dmg');
    const releases = path.join(downloads.dir, 'releases.json');
    fs.writeFileSync(artifact, 'fake-dmg-for-test');
    fs.writeFileSync(releases, JSON.stringify({ version: '1.0.0', downloads: { mac: 'https://example.com/aura.dmg' } }));
    process.env.AURA_LOCAL_MAC_ARTIFACT = artifact;

    const res = await request(createServer({ releasesPath: releases, downloadsPath: downloads.file }), 'GET', '/api/download?os=mac');
    const body = await res.text();

    expect(res.status).toBe(200);
    expect(res.headers.get('content-disposition')).toContain('AURA-test.dmg');
    expect(body).toBe('fake-dmg-for-test');
    expect(JSON.parse(fs.readFileSync(downloads.file, 'utf-8')).mac).toBe(1);
  });

  it('redirects download requests to configured hosted artifacts', async () => {
    const downloads = tempJson({ mac: 0, windows: 0, linux: 0 });
    const releases = path.join(downloads.dir, 'releases.json');
    fs.writeFileSync(releases, JSON.stringify({ downloads: { mac: 'https://cdn.example.net/AURA.dmg' } }));

    const res = await request(createServer({ releasesPath: releases, downloadsPath: downloads.file }), 'GET', '/api/download?os=mac');

    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toBe('https://cdn.example.net/AURA.dmg');
  });

  it('exposes launch health and private-alpha update metadata', async () => {
    const downloads = tempJson({ mac: 0, windows: 0, linux: 0 });
    const artifact = path.join(downloads.dir, 'AURA-test.dmg');
    const releases = path.join(downloads.dir, 'releases.json');
    fs.writeFileSync(artifact, 'fake');
    fs.writeFileSync(releases, JSON.stringify({ version: '1.2.0', channel: 'private-alpha', notes: 'test build', downloads: { mac: '/api/download?os=mac' } }));
    process.env.AURA_LOCAL_MAC_ARTIFACT = artifact;

    const health = await request(createServer({ releasesPath: releases, downloadsPath: downloads.file }), 'GET', '/api/launch/health');
    const healthBody = await health.json();
    expect(health.status).toBe(200);
    expect(healthBody.configured.mac_download).toBe(true);

    const update = await request(createServer({ releasesPath: releases, downloadsPath: downloads.file }), 'GET', '/api/updates/latest?platform=darwin&arch=arm64&version=1.0.0');
    const body = await update.json();
    expect(body.version).toBe('1.2.0');
    expect(body.update_available).toBe(true);
    expect(body.download_url).toBe('/api/download?os=mac');
  });

  it('records crash reports with secret redaction', async () => {
    const { store } = tempStore();
    const res = await request(createServer({ store }), 'POST', '/api/crash-reports', {
      message: 'renderer failed',
      stack: 'password=test123 sk_test_abc',
    });
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.ok).toBe(true);
    expect(JSON.stringify(body.report)).not.toContain('test123');
    expect(JSON.stringify(body.report)).not.toContain('sk_test_abc');
  });

  it('activates devices with signed tokens and enforces seat limits', async () => {
    const { privateKey } = crypto.generateKeyPairSync('ed25519');
    process.env.AURA_VENDOR_PRIVATE_KEY = privateKey.export({ type: 'pkcs8', format: 'pem' });
    const issued = issueLicenseToken({ email: 'alpha@example.com' });
    const { store } = tempStore();
    const server = createServer({ store });

    const first = await request(server, 'POST', '/api/devices/activate', {
      token: issued.token,
      device_fingerprint: 'mac-1',
      device_name: 'Founder Mac',
    });
    const firstBody = await first.json();
    expect(first.status).toBe(200);
    expect(firstBody.ok).toBe(true);

    const second = await request(createServer({ store }), 'POST', '/api/devices/activate', {
      token: issued.token,
      device_fingerprint: 'mac-2',
      device_name: 'Second Mac',
    });
    const secondBody = await second.json();
    expect(second.status).toBe(409);
    expect(secondBody.status).toBe('seat_limit_reached');
  });
});
