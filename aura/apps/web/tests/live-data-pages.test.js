import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

describe('live data dashboard pages', () => {
  it('does not import static sample repos or findings', () => {
    const dashboard = fs.readFileSync(path.resolve(process.cwd(), 'app/dashboard/page.tsx'), 'utf-8');
    const repos = fs.readFileSync(path.resolve(process.cwd(), 'app/repos/page.tsx'), 'utf-8');
    expect(dashboard).toContain('backendGet');
    expect(repos).toContain('backendGet');
    expect(dashboard).not.toContain('sampleFindings');
    expect(repos).not.toContain('sampleRepos');
  });

  it('audit page includes grounded audit chatbot language', () => {
    const audit = fs.readFileSync(path.resolve(process.cwd(), 'app/audit/page.tsx'), 'utf-8');
    expect(audit).toContain('Audit chatbot');
    expect(audit).toContain('grounded only in your workspace records');
  });
});
