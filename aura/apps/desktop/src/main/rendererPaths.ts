import fs from 'fs';
import path from 'path';

export function productionRendererPath(mainDir: string) {
  return path.join(mainDir, '../../dist/index.html');
}

export function rendererFallbackHtml(detail: string) {
  const safeDetail = detail.replace(/[<>&]/g, (char) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[char] || char));
  return [
    '<!doctype html>',
    '<html>',
    '<head><meta charset="utf-8"><title>Aegisure startup issue</title></head>',
    '<body style="font-family: system-ui, sans-serif; margin: 40px; color: #172033;">',
    '<h1>Aegisure could not load the desktop UI</h1>',
    '<p>The packaged renderer was not found or could not be loaded. This build should show this message instead of a blank white screen.</p>',
    `<pre style="white-space: pre-wrap; background: #f6f8fb; border: 1px solid #d7dee8; border-radius: 8px; padding: 12px;">${safeDetail}</pre>`,
    '<p>From a fresh clone, run <code>pnpm aura:package</code> again and reopen the generated DMG.</p>',
    '</body>',
    '</html>',
  ].join('');
}

export function rendererFallbackUrl(detail: string) {
  return `data:text/html;charset=utf-8,${encodeURIComponent(rendererFallbackHtml(detail))}`;
}

export function rendererExists(mainDir: string) {
  return fs.existsSync(productionRendererPath(mainDir));
}
