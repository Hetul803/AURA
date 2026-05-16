import { afterEach, describe, expect, it } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { createServer, incrementDownload, issueLicenseToken } from '../src/server.js';

function tempJson(initial) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'aura-web-test-'));
  const file = path.join(dir, 'downloads.json');
  fs.writeFileSync(file, JSON.stringify(initial, null, 2));
  return { dir, file };
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
      });
      call.then(resolve).catch(reject).finally(() => server.close());
    });
  });
}

afterEach(() => {
  delete process.env.AURA_VENDOR_PRIVATE_KEY;
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
});
