#!/usr/bin/env node
const { execFileSync } = require('node:child_process');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const desktop = path.join(root, 'apps', 'desktop');

function run(command, args, options = {}) {
  execFileSync(command, args, {
    cwd: options.cwd || root,
    stdio: 'inherit',
    env: process.env,
  });
}

console.log('==> Verifying Electron install');
run('node', ['-e', "const electron = require('electron'); if (!electron) process.exit(1); console.log('electron:', electron);"], { cwd: desktop });

console.log('==> Verifying esbuild/Vite renderer build');
run('pnpm', ['--filter', 'aura-desktop', 'build']);

console.log('Electron and renderer build verified.');
