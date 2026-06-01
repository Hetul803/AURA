import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

describe('Supabase auth page', () => {
  it('exposes GitHub OAuth login copy', () => {
    const page = fs.readFileSync(path.resolve(process.cwd(), 'app/auth/page.tsx'), 'utf-8');
    expect(page).toContain('Sign in with GitHub');
    expect(page).toContain('NEXT_PUBLIC_SUPABASE_URL');
  });
});
