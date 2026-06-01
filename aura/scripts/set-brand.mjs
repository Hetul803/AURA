#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const root = process.cwd();
const args = Object.fromEntries(process.argv.slice(2).map((arg) => {
  const [key, ...rest] = arg.replace(/^--/, '').split('=');
  return [key, rest.join('=') || ''];
}));

const productName = args.name || args.product;
if (!productName) {
  console.error('Usage: node scripts/set-brand.mjs --name="Your App Name" [--company="Your Company"] [--app-id="com.company.app"]');
  process.exit(1);
}

const companyName = args.company || `${productName} Labs`;
const appId = args['app-id'] || `com.${companyName.toLowerCase().replace(/[^a-z0-9]+/g, '')}.${productName.toLowerCase().replace(/[^a-z0-9]+/g, '')}`;
const artifactPrefix = productName.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'Aegisure';

const brandPath = path.join(root, 'config', 'brand.json');
const brand = JSON.parse(fs.readFileSync(brandPath, 'utf8'));
Object.assign(brand, {
  product_name: productName,
  assistant_default_name: productName,
  company_name: companyName,
  app_id: appId,
  artifact_name: `${artifactPrefix}-\${version}-\${os}-\${arch}.\${ext}`,
});
fs.writeFileSync(brandPath, `${JSON.stringify(brand, null, 2)}\n`);

const builderPath = path.join(root, 'apps', 'desktop', 'electron-builder.yml');
let builder = fs.readFileSync(builderPath, 'utf8');
builder = builder.replace(/^appId: .+$/m, `appId: ${appId}`);
builder = builder.replace(/^productName: .+$/m, `productName: ${productName}`);
builder = builder.replace(/^artifactName: .+$/m, `artifactName: ${artifactPrefix}-\${version}-\${os}-\${arch}.\${ext}`);
fs.writeFileSync(builderPath, builder);

console.log(`Brand updated:
  productName: ${productName}
  companyName: ${companyName}
  appId: ${appId}
  artifactName: ${artifactPrefix}-\${version}-\${os}-\${arch}.\${ext}

Next:
  pnpm aura:package
`);
