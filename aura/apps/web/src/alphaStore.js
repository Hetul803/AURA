import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

function now() {
  return new Date().toISOString();
}

function emptyStore() {
  return {
    accounts: {},
    licenses: {},
    activations: {},
    checkout_sessions: {},
    crashes: [],
    events: [],
  };
}

export class AlphaStore {
  constructor(filePath) {
    this.filePath = filePath;
  }

  read() {
    try {
      return { ...emptyStore(), ...JSON.parse(fs.readFileSync(this.filePath, 'utf-8')) };
    } catch {
      return emptyStore();
    }
  }

  write(data) {
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
    fs.writeFileSync(this.filePath, JSON.stringify(data, null, 2));
    return data;
  }

  transact(mutator) {
    const data = this.read();
    const result = mutator(data);
    this.write(data);
    return result;
  }

  upsertAccount(email, patch = {}) {
    const normalized = String(email || '').trim().toLowerCase();
    if (!normalized) throw new Error('email_required');
    return this.transact((data) => {
      const existing = data.accounts[normalized] || { email: normalized, created_at: now() };
      data.accounts[normalized] = { ...existing, ...patch, email: normalized, updated_at: now() };
      return data.accounts[normalized];
    });
  }

  storeCheckoutSession(session) {
    return this.transact((data) => {
      data.checkout_sessions[session.id] = { ...session, updated_at: now() };
      data.events.push({ type: 'checkout_session_stored', session_id: session.id, created_at: now() });
      return data.checkout_sessions[session.id];
    });
  }

  storeLicense(payload, token, metadata = {}) {
    return this.transact((data) => {
      const record = {
        license_id: payload.license_id,
        account_email: payload.account_email,
        tier: payload.tier,
        seats: payload.seats || 1,
        status: metadata.status || 'active',
        token,
        token_hash: crypto.createHash('sha256').update(token).digest('hex'),
        features: payload.features || {},
        expires_at: payload.expires_at || null,
        issued_at: payload.issued_at || now(),
        metadata,
        updated_at: now(),
      };
      data.licenses[payload.license_id] = record;
      data.events.push({ type: 'license_issued', license_id: payload.license_id, account_email: payload.account_email, created_at: now() });
      return record;
    });
  }

  getLicense(licenseId) {
    return this.read().licenses[licenseId] || null;
  }

  activeActivationsForLicense(licenseId) {
    return Object.values(this.read().activations).filter((item) => item.license_id === licenseId && item.status === 'active');
  }

  activateDevice(license, device) {
    return this.transact((data) => {
      const active = Object.values(data.activations).filter((item) => item.license_id === license.license_id && item.status === 'active');
      const existing = active.find((item) => item.device_fingerprint === device.device_fingerprint);
      if (existing) {
        existing.last_seen_at = now();
        existing.device_name = device.device_name || existing.device_name;
        return { ok: true, reused: true, activation: existing };
      }
      if (active.length >= Number(license.seats || 1)) {
        return {
          ok: false,
          status: 'seat_limit_reached',
          message: `This license allows ${license.seats || 1} active device(s). Revoke an old device before activating another.`,
        };
      }
      const activation = {
        activation_id: `act_${crypto.randomUUID().replace(/-/g, '')}`,
        license_id: license.license_id,
        account_email: license.account_email,
        device_fingerprint: device.device_fingerprint,
        device_name: device.device_name || 'Unknown device',
        status: 'active',
        activated_at: now(),
        last_seen_at: now(),
        metadata: device.metadata || {},
      };
      data.activations[activation.activation_id] = activation;
      data.events.push({ type: 'device_activated', activation_id: activation.activation_id, license_id: license.license_id, created_at: now() });
      return { ok: true, activation };
    });
  }

  revokeActivation(activationId, reason = 'manual') {
    return this.transact((data) => {
      const activation = data.activations[activationId];
      if (!activation) return { ok: false, status: 'not_found' };
      activation.status = 'revoked';
      activation.revoked_at = now();
      activation.revocation_reason = reason;
      data.events.push({ type: 'device_revoked', activation_id: activationId, reason, created_at: now() });
      return { ok: true, activation };
    });
  }

  recordCrash(report) {
    return this.transact((data) => {
      const item = {
        crash_id: `crash_${crypto.randomUUID().replace(/-/g, '')}`,
        ...report,
        created_at: now(),
      };
      data.crashes.unshift(item);
      data.crashes = data.crashes.slice(0, 1000);
      return item;
    });
  }
}

