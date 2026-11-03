const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const root = path.resolve(__dirname, '..');
const target = path.join(root, '.env');
if (fs.existsSync(target)) {
  console.log('Existing .env preserved. Compare it with .env.example before starting.');
} else {
  const secret = () => crypto.randomBytes(32).toString('hex');
  const password = secret();
  const text = fs.readFileSync(path.join(root, '.env.example'), 'utf8')
    .replace(/^JWT_SECRET=$/m, `JWT_SECRET=${secret()}`)
    .replace(/^INTERNAL_API_TOKEN=$/m, `INTERNAL_API_TOKEN=${secret()}`)
    .replace(/^POSTGRES_PASSWORD=$/m, `POSTGRES_PASSWORD=${password}`);
  fs.writeFileSync(target, `${text}\nDATABASE_URL=postgresql://research:${password}@localhost:5432/research_paper_analyzer\n`, { flag: 'wx', mode: 0o600 });
  console.log('Created .env with fresh secrets. Do not commit or share it.');
}
