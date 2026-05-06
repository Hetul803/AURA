import fs from 'fs';
import os from 'os';
import path from 'path';
import { afterEach, describe, expect, it } from 'vitest';
import { backendCandidates, findBackendDir } from '../src/main/backendPaths';
import { productionRendererPath, rendererFallbackHtml, rendererFallbackUrl } from '../src/main/rendererPaths';

let tempRoot = '';

function makeTempRoot() {
  tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'aura-startup-'));
  return tempRoot;
}

afterEach(() => {
  if (tempRoot) fs.rmSync(tempRoot, { recursive: true, force: true });
  tempRoot = '';
});

describe('desktop startup paths', () => {
  it('finds a packaged backend under Electron resources', () => {
    const root = makeTempRoot();
    const backend = path.join(root, 'resources', 'backend');
    fs.mkdirSync(path.join(backend, 'src', 'api'), { recursive: true });
    fs.writeFileSync(path.join(backend, 'src', 'api', 'main.py'), '');

    expect(findBackendDir({
      cwd: path.join(root, 'somewhere'),
      appPath: path.join(root, 'AURA.app', 'Contents', 'Resources', 'app.asar'),
      resourcesPath: path.join(root, 'resources'),
    })).toBe(backend);
  });

  it('looks for fresh-clone backends from repo and app paths', () => {
    const root = makeTempRoot();
    const candidates = backendCandidates({
      cwd: path.join(root, 'AURA', 'aura'),
      appPath: path.join(root, 'AURA', 'aura', 'apps', 'desktop'),
    });

    expect(candidates).toContain(path.join(root, 'AURA', 'aura', 'apps', 'backend'));
  });

  it('points production Electron at the built renderer index', () => {
    expect(productionRendererPath('/repo/aura/apps/desktop/dist-electron/main')).toBe('/repo/aura/apps/desktop/dist/index.html');
  });

  it('uses a startup fallback that explains renderer load failure', () => {
    const html = rendererFallbackHtml('Missing <renderer>');
    expect(html).toContain('AURA could not load the desktop UI');
    expect(html).toContain('Missing &lt;renderer&gt;');
    expect(rendererFallbackUrl('missing')).toMatch(/^data:text\/html/);
  });

  it('keeps packaged renderer assets relative and has a visible boot fallback', () => {
    const viteConfig = fs.readFileSync(path.join(process.cwd(), 'vite.config.ts'), 'utf8');
    const indexHtml = fs.readFileSync(path.join(process.cwd(), 'index.html'), 'utf8');
    expect(viteConfig).toContain("base: './'");
    expect(indexHtml).toContain('AURA is starting.');
    expect(indexHtml).toContain('boot-fallback');
  });

  it('packages the preload bridge as CommonJS so Electron can load it', () => {
    const mainSource = fs.readFileSync(path.join(process.cwd(), 'src/main/index.ts'), 'utf8');
    const preloadBridge = fs.readFileSync(path.join(process.cwd(), 'src/main/preload.cjs'), 'utf8');
    const packageJson = fs.readFileSync(path.join(process.cwd(), 'package.json'), 'utf8');
    expect(mainSource).toContain('preload.cjs');
    expect(preloadBridge).toContain("require('electron')");
    expect(packageJson).toContain('scripts/copy-preload.mjs');
  });
});
