import fs from 'fs';
import path from 'path';

function hasBackend(candidate: string) {
  return fs.existsSync(path.join(candidate, 'src', 'api', 'main.py'));
}

function walkForBackend(start: string) {
  const found: string[] = [];
  let current = start;
  for (let i = 0; i < 8; i += 1) {
    found.push(path.join(current, 'aura', 'apps', 'backend'));
    found.push(path.join(current, 'apps', 'backend'));
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return found;
}

export function backendCandidates(options: { cwd: string; appPath: string; resourcesPath?: string; envBackendDir?: string }) {
  const candidates = [
    options.envBackendDir,
    options.resourcesPath ? path.join(options.resourcesPath, 'backend') : undefined,
    ...walkForBackend(options.cwd),
    ...walkForBackend(options.appPath),
  ].filter(Boolean) as string[];
  return [...new Set(candidates)];
}

export function findBackendDir(options: { cwd: string; appPath: string; resourcesPath?: string; envBackendDir?: string }) {
  return backendCandidates(options).find(hasBackend) || null;
}
