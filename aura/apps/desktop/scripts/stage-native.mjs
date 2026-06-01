import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const desktopRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(desktopRoot, '..', '..');
const nativeRoot = path.join(desktopRoot, 'native');
const stageRoot = path.join(desktopRoot, 'build-resources', 'native');
const helper = path.join(nativeRoot, 'macos', 'build', 'AURASpeechHelper');

fs.rmSync(stageRoot, { recursive: true, force: true });
fs.mkdirSync(stageRoot, { recursive: true });

if (fs.existsSync(helper)) {
  fs.copyFileSync(helper, path.join(stageRoot, 'AURASpeechHelper'));
  fs.chmodSync(path.join(stageRoot, 'AURASpeechHelper'), 0o755);
  console.log(`Staged native speech helper at ${stageRoot}`);
} else {
  fs.writeFileSync(
    path.join(stageRoot, 'README.txt'),
    [
      'Aegisure native helper staging area.',
      '',
      'AURASpeechHelper was not built.',
      'Run scripts/build-macos-speech-helper.sh before packaging to include native push-to-talk speech recognition.',
      `Expected source: ${path.join(repoRoot, 'apps/desktop/native/macos/AURASpeechHelper.swift')}`,
    ].join('\n'),
    'utf8',
  );
  console.warn('Native speech helper not built; packaged app will show typed fallback for voice input.');
}

