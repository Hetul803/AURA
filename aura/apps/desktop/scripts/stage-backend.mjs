import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const desktopRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(desktopRoot, '..', '..');
const backendRoot = path.join(repoRoot, 'apps', 'backend');
const stageRoot = path.join(desktopRoot, 'build-resources', 'backend');

const entriesToCopy = [
  'README.md',
  'pyproject.toml',
  'requirements-private-alpha.txt',
  'fixtures',
  'src',
];

function copyEntry(relativePath) {
  const source = path.join(backendRoot, relativePath);
  const destination = path.join(stageRoot, relativePath);
  if (!fs.existsSync(source)) {
    throw new Error(`Missing backend resource: ${relativePath}`);
  }
  fs.cpSync(source, destination, { recursive: true });
}

fs.rmSync(stageRoot, { recursive: true, force: true });
fs.mkdirSync(stageRoot, { recursive: true });

for (const entry of entriesToCopy) copyEntry(entry);

fs.rmSync(path.join(stageRoot, 'src', 'aura_backend.egg-info'), { recursive: true, force: true });
fs.writeFileSync(
  path.join(stageRoot, 'PRIVATE_ALPHA_BUNDLE.txt'),
  [
    'AURA Mac private-alpha backend bundle',
    '',
    'This bundle contains the backend source used by the packaged desktop app.',
    'Runtime expectation:',
    '- macOS',
    '- local Python 3.10+',
    '- `python3 -m pip install -r requirements-private-alpha.txt`',
    '- `python3 -m playwright install chromium` if you want browser/research flows',
    '- local Ollama installed and running for real drafting',
  ].join('\n'),
  'utf8',
);

console.log(`Staged backend bundle at ${stageRoot}`);
