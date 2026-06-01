import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { execSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const packageJson = JSON.parse(readFileSync(path.join(__dirname, 'package.json'), 'utf8'));

function gitCommit() {
  try {
    return execSync('git rev-parse --short HEAD', { cwd: path.join(__dirname, '..', '..'), stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
  } catch {
    return 'unknown';
  }
}

const buildTimestamp = new Date().toISOString();

export default defineConfig({
  base: './',
  plugins: [react()],
  server: { port: 5173 },
  define: {
    __AEGISURE_BUILD_INFO__: JSON.stringify({
      appVersion: packageJson.version,
      gitCommit: gitCommit(),
      buildTimestamp,
      rendererBuildTimestamp: buildTimestamp,
    }),
  },
});
