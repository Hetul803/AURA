import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';
import { incrementDownload } from '../src/server.js';

describe('download counter', () => {
  it('increments', () => {
    const p = path.resolve('../../infra/releases/downloads.json');
    const before = JSON.parse(fs.readFileSync(p, 'utf-8'));
    incrementDownload('mac');
    const after = JSON.parse(fs.readFileSync(p, 'utf-8'));
    expect(after.mac).toBe(before.mac + 1);
  });
});
