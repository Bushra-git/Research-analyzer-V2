const { test } = require('node:test');
const assert = require('node:assert/strict');
const jwt = require('jsonwebtoken');
const { createApp, configuration } = require('../server');
const config = { jwtSecret: 'j'.repeat(48), internalToken: 'i'.repeat(48), flaskUrl: 'http://private',
  origins: ['http://localhost:3000'], trustedProxies: false, guestLimit: 2, retentionHours: 24, secureCookies: false };
const cookie = id => 'research_session=' + jwt.sign({ sub: id, kind: 'guest' }, config.jwtSecret,
  { issuer: 'research-analyzer', audience: 'browser', expiresIn: '1d' });
async function fixture(t, overrides = {}) {
  const records = [{ jobId: 'job-a', ownerKey: 'guest:alice', expiresAt: new Date(Date.now() + 100000), status: 'finished', result: { summary: 'private' } }];
  const calls = [];
  const prisma = {
    user: { findUnique: async () => null }, guestUsage: { findUnique: async () => null },
    analysis: {
      findFirst: async ({ where }) => records.find(r => r.jobId === where.jobId && r.ownerKey === where.ownerKey),
      findMany: async ({ where }) => { calls.push(where); return records.filter(r => r.ownerKey === where.ownerKey); },
      updateMany: async args => { calls.push(args); throw new Error('Completed GET must not change ownership'); },
      deleteMany: async ({ where }) => { const i = records.findIndex(r => r.jobId === where.jobId && r.ownerKey === where.ownerKey); if (i >= 0) records.splice(i, 1); },
    }, ...overrides,
  };
  const http = { get: async () => { throw new Error('Must not call internal service'); }, delete: async () => ({ data: { ok: true } }) };
  const server = createApp({ prisma, config, http }).listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = (path, id, options = {}) => fetch(base + path, { ...options, headers: { cookie: cookie(id), ...options.headers } });
  return { request, base, records, calls };
}
test('guest history never includes another guest', async t => {
  const f = await fixture(t);
  assert.deepEqual((await (await f.request('/api/history', 'bob')).json()).history, []);
  assert.equal((await (await f.request('/api/history', 'alice')).json()).history.length, 1);
});
test('job ownership is checked before status or deletion', async t => {
  const f = await fixture(t);
  assert.equal((await f.request('/api/status/job-a', 'bob')).status, 404);
  assert.equal((await f.request('/api/analyses/job-a', 'bob', { method: 'DELETE' })).status, 404);
  assert.equal(f.records.length, 1);
});
test('owner reads result without changing ownership', async t => {
  const f = await fixture(t);
  const response = await f.request('/api/status/job-a', 'alice');
  assert.equal(response.status, 200);
  assert.equal((await response.json()).result.summary, 'private');
  assert.equal(f.records[0].ownerKey, 'guest:alice');
});
test('owner can delete a result', async t => {
  const f = await fixture(t);
  assert.equal((await f.request('/api/analyses/job-a', 'alice', { method: 'DELETE' })).status, 200);
  assert.equal(f.records.length, 0);
});
test('forged cookie and cross-origin mutations are rejected', async t => {
  const f = await fixture(t);
  assert.equal((await fetch(f.base + '/api/history', { headers: { cookie: 'research_session=forged' } })).status, 401);
  assert.equal((await f.request('/api/auth/logout', 'alice', { method: 'POST', headers: { origin: 'https://attacker.invalid' } })).status, 403);
});
test('new sessions use HttpOnly SameSite cookies', async t => {
  const f = await fixture(t);
  const response = await fetch(f.base + '/api/session');
  assert.match(response.headers.get('set-cookie'), /HttpOnly/);
  assert.match(response.headers.get('set-cookie'), /SameSite=Strict/);
});
test('invalid history limits rejected', async t => {
  const f = await fixture(t);
  for (const value of ['-1', 'NaN', '1.5', '101']) assert.equal((await f.request('/api/history?limit=' + value, 'alice')).status, 400);
});
test('development secrets refused', () => {
  assert.throws(() => configuration({ JWT_SECRET: 'change-this-development-secret' }), /JWT_SECRET/);
});
