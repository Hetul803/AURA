import http from 'http';
import fs from 'fs';
import path from 'path';

const releasesPath = path.resolve('../../infra/releases/releases.json');
const downloadsPath = path.resolve('../../infra/releases/downloads.json');

export function incrementDownload(os) {
  const data = JSON.parse(fs.readFileSync(downloadsPath, 'utf-8'));
  data[os] = (data[os] || 0) + 1;
  fs.writeFileSync(downloadsPath, JSON.stringify(data, null, 2));
  return data;
}

const landing = `<!doctype html><h1>AURA</h1><a href='/downloads'>Downloads</a>`;
const downloadsPage = `<!doctype html><h1>Downloads</h1><button>Mac</button><button>Windows</button>`;

const server = http.createServer((req, res) => {
  if (req.url === '/') return res.end(landing);
  if (req.url === '/downloads') return res.end(downloadsPage);
  if (req.url === '/api/releases') return res.end(fs.readFileSync(releasesPath));
  if (req.url?.startsWith('/api/download?os=')) {
    const os = new URL(req.url, 'http://localhost').searchParams.get('os') || 'unknown';
    res.setHeader('content-type', 'application/json');
    return res.end(JSON.stringify(incrementDownload(os)));
  }
  res.statusCode = 404; res.end('not found');
});

if (process.env.NODE_ENV !== 'test') {
  server.listen(3000, () => console.log('web on 3000'));
}

export default server;
