const express = require('express');
const axios = require('axios');
const cors = require('cors');
const multer = require('multer');
const FormData = require('form-data');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const crypto = require('crypto');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
require('dotenv').config();
require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });
const COOKIE = 'research_session';
const fail = (status, message) => Object.assign(new Error(message), { status });

function configuration(env = process.env) {
  for (const name of ['JWT_SECRET', 'INTERNAL_API_TOKEN']) {
    if (!env[name] || env[name].length < 32 || /change-this|replace-with/.test(env[name])) throw new Error(`${name} must be a random secret of at least 32 characters`);
  }
  if (!env.FLASK_API_URL) throw new Error('FLASK_API_URL is required');
  const guestLimit = Number(env.GUEST_ANALYZE_LIMIT || 2);
  const retentionHours = Number(env.RETENTION_HOURS || 24);
  if (!Number.isInteger(guestLimit) || guestLimit < 1 || !Number.isInteger(retentionHours) || retentionHours < 1 || retentionHours > 168) throw new Error('Invalid guest limit or retention hours (1–168)');
  return { jwtSecret: env.JWT_SECRET, internalToken: env.INTERNAL_API_TOKEN,
    flaskUrl: env.FLASK_API_URL, secureCookies: env.NODE_ENV === 'production',
    origins: (env.ALLOWED_ORIGINS || 'http://localhost:3000').split(',').map(s => s.trim()),
    trustedProxies: env.TRUSTED_PROXIES ? env.TRUSTED_PROXIES.split(',') : false,
    guestLimit, retentionHours };
}
function createApp({ prisma, http = axios, config = configuration() }) {
  const app = express();
  app.set('trust proxy', config.trustedProxies);
  app.use(helmet());
  app.use(cors({ origin: config.origins, credentials: true, methods: ['GET', 'POST', 'DELETE'], exposedHeaders: ['X-Guest-Analyses-Used', 'X-Guest-Analyses-Limit'] }));
  app.use(express.json({ limit: '256kb' }));
  app.use((req, res, next) => {
    res.set('Cache-Control', 'no-store');
    if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method) && req.headers.origin && !config.origins.includes(req.headers.origin)) return next(fail(403, 'Origin not allowed'));
    next();
  });
  const expensiveLimit = rateLimit({ windowMs: 900000, limit: 30, standardHeaders: 'draft-7', legacyHeaders: false });
  const authLimit = rateLimit({ windowMs: 900000, limit: 20, standardHeaders: 'draft-7', legacyHeaders: false });
  const readLimit = rateLimit({ windowMs: 60000, limit: 120, standardHeaders: 'draft-7', legacyHeaders: false });
  const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 15 * 1024 * 1024, files: 1, fields: 2 } });
  function setSession(res, claims) {
    res.cookie(COOKIE, jwt.sign(claims, config.jwtSecret, { expiresIn: '1d', issuer: 'research-analyzer', audience: 'browser' }),
      { httpOnly: true, secure: config.secureCookies, sameSite: 'strict', path: '/', maxAge: 86400000 });
  }
  async function identity(req, res, next) {
    try {
      const part = (req.headers.cookie || '').split(';').map(s => s.trim()).find(s => s.startsWith(`${COOKIE}=`));
      let claims;
      if (part) {
        try { claims = jwt.verify(decodeURIComponent(part.slice(COOKIE.length + 1)), config.jwtSecret, { algorithms: ['HS256'], issuer: 'research-analyzer', audience: 'browser' }); }
        catch { res.clearCookie(COOKIE, { path: '/' }); throw fail(401, 'Session expired. Refresh and sign in again.'); }
      }
      if (!claims) { claims = { sub: crypto.randomUUID(), kind: 'guest' }; setSession(res, claims); }
      if (!['guest', 'user'].includes(claims.kind) || typeof claims.sub !== 'string') throw fail(401, 'Invalid session');
      if (claims.kind === 'user') {
        req.user = await prisma.user.findUnique({ where: { id: claims.sub }, select: { id: true, email: true, name: true } });
        if (!req.user) throw fail(401, 'Account no longer exists');
      }
      req.ownerKey = `${claims.kind}:${claims.sub}`;
      req.quotaKey = crypto.createHmac('sha256', config.jwtSecret).update(req.ip || 'unknown').digest('hex');
      next();
    } catch (error) { next(error); }
  }
  app.use('/api', identity);
  const internal = ownerKey => ({ 'X-Internal-Token': config.internalToken, 'X-Owner-Key': ownerKey });
  async function owned(req) {
    const row = await prisma.analysis.findFirst({ where: { jobId: req.params.jobId, ownerKey: req.ownerKey, expiresAt: { gt: new Date() } } });
    if (!row) throw fail(404, 'Analysis not found');
    return row;
  }
  app.get('/api/session', readLimit, async (req, res) => {
    const usage = req.user ? null : await prisma.guestUsage.findUnique({ where: { ip: req.quotaKey } });
    res.json({ user: req.user || null, guestUsed: usage?.analysesUsed || 0, guestLimit: config.guestLimit, retentionHours: config.retentionHours });
  });
  app.post('/api/auth/logout', (req, res) => { setSession(res, { sub: crypto.randomUUID(), kind: 'guest' }); res.json({ ok: true }); });
  app.post('/api/auth/register', authLimit, async (req, res) => {
    const { password, name } = req.body || {};
    const email = typeof req.body?.email === 'string' ? req.body.email.trim().toLowerCase() : '';
    if (!/^\S+@\S+\.\S+$/.test(email) || email.length > 254 || typeof password !== 'string' || password.length < 10 || Buffer.byteLength(password) > 72 || (name != null && (typeof name !== 'string' || name.length > 100))) throw fail(400, 'Use a valid email, a 10–72 byte password, and a name up to 100 characters');
    try {
      const user = await prisma.user.create({ data: { email, name: name?.trim() || null, passwordHash: await bcrypt.hash(password, 12) }, select: { id: true, email: true, name: true } });
      setSession(res, { sub: user.id, kind: 'user' }); res.status(201).json({ user });
    } catch (error) { if (error.code === 'P2002') throw fail(409, 'Email is already registered'); throw error; }
  });
  app.post('/api/auth/login', authLimit, async (req, res) => {
    const email = typeof req.body?.email === 'string' ? req.body.email.trim().toLowerCase() : '';
    const password = req.body?.password;
    if (typeof password !== 'string' || Buffer.byteLength(password) > 72 || email.length > 254) throw fail(400, 'Invalid credentials');
    const user = await prisma.user.findUnique({ where: { email } });
    if (!user?.passwordHash || !await bcrypt.compare(password, user.passwordHash)) throw fail(401, 'Invalid email or password');
    setSession(res, { sub: user.id, kind: 'user' }); res.json({ user: { id: user.id, email: user.email, name: user.name } });
  });
  app.post('/api/analyze', expensiveLimit, upload.single('file'), async (req, res) => {
    if (!req.file || req.file.buffer.subarray(0, 5).toString() !== '%PDF-') throw fail(400, 'Upload a valid PDF file');
    const jobId = crypto.randomUUID();
    let reserved = false, used = 0;
    if (!req.user) {
      const rows = await prisma.$queryRaw`
        INSERT INTO guest_usage (ip, analyses_used, updated_at) VALUES (${req.quotaKey}, 1, NOW())
        ON CONFLICT (ip) DO UPDATE SET analyses_used = guest_usage.analyses_used + 1, updated_at = NOW()
        WHERE guest_usage.analyses_used < ${config.guestLimit} RETURNING analyses_used`;
      if (!rows.length) return res.status(403).json({ error: 'Guest limit reached. Sign in to continue.', requiresAuth: true });
      reserved = true; used = rows[0].analyses_used;
    }
    const filename = req.file.originalname.replace(/[\x00-\x1f\/\\]/g, '_').slice(0, 200);
    try {
      await prisma.analysis.create({ data: { jobId, ownerKey: req.ownerKey, userId: req.user?.id || null, paperFilename: filename,
        features: {}, summary: '', status: 'queued', expiresAt: new Date(Date.now() + config.retentionHours * 3600000) } });
      const form = new FormData();
      form.append('file', req.file.buffer, filename);
      form.append('external_search', req.body.external_search === 'true' ? 'true' : 'false');
      const response = await http.post(`${config.flaskUrl}/analyze`, form, { headers: { ...form.getHeaders(), ...internal(req.ownerKey), 'X-Job-Id': jobId }, timeout: 15000 });
      res.set('X-Guest-Analyses-Used', String(used)).set('X-Guest-Analyses-Limit', String(config.guestLimit));
      res.status(202).json(response.data);
    } catch (error) {
      if (!error.response && ['ECONNABORTED', 'ECONNRESET'].includes(error.code)) return res.status(202).json({ job_id: jobId, status: 'queued', message: 'Submission uncertain; checking job status.' });
      await prisma.analysis.deleteMany({ where: { jobId, ownerKey: req.ownerKey } });
      if (reserved) await prisma.guestUsage.updateMany({ where: { ip: req.quotaKey, analysesUsed: { gt: 0 } }, data: { analysesUsed: { decrement: 1 } } });
      throw error;
    }
  });
  app.get('/api/status/:jobId', readLimit, async (req, res) => {
    const row = await owned(req);
    if (row.result || ['cancelled', 'failed'].includes(row.status)) return res.json({ job_id: row.jobId, status: row.status, result: row.result });
    const { data } = await http.get(`${config.flaskUrl}/status/${req.params.jobId}`, { headers: internal(req.ownerKey), timeout: 15000 });
    if (['finished', 'failed', 'cancelled'].includes(data.status)) await prisma.analysis.updateMany({ where: { jobId: row.jobId, ownerKey: req.ownerKey }, data: { status: data.status,
      ...(data.result ? { result: data.result, features: data.result.features || {}, summary: data.result.summary || '' } : {}) } });
    res.json(data);
  });
  app.delete('/api/analyses/:jobId', readLimit, async (req, res) => {
    await owned(req);
    await http.delete(`${config.flaskUrl}/jobs/${req.params.jobId}`, { headers: internal(req.ownerKey), timeout: 15000 });
    await prisma.analysis.deleteMany({ where: { jobId: req.params.jobId, ownerKey: req.ownerKey } });
    res.json({ ok: true });
  });
  app.post('/api/venues', readLimit, async (req, res) => {
    const { data } = await http.post(`${config.flaskUrl}/venues`, req.body, { headers: internal(req.ownerKey), timeout: 30000 });
    res.json(data);
  });
  app.post('/api/recommend', expensiveLimit, async (req, res) => {
    const jobId = req.body?.job_id;
    if (typeof jobId !== 'string') throw fail(400, 'job_id is required');
    const row = await prisma.analysis.findFirst({ where: { jobId, ownerKey: req.ownerKey, expiresAt: { gt: new Date() } } });
    if (!row) throw fail(404, 'Analysis not found');
    const { data } = await http.post(`${config.flaskUrl}/recommend`, req.body, { headers: internal(req.ownerKey), timeout: 120000 });
    res.json(data);
  });
  app.get('/api/history', readLimit, async (req, res) => {
    const limit = Number(req.query.limit || 25);
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) throw fail(400, 'limit must be 1–100');
    const history = await prisma.analysis.findMany({ where: { ownerKey: req.ownerKey, expiresAt: { gt: new Date() } }, orderBy: { createdAt: 'desc' }, take: limit,
      select: { jobId: true, paperFilename: true, createdAt: true, expiresAt: true, status: true, summary: true } });
    res.json({ history });
  });
  app.use((error, req, res, next) => {
    if (res.headersSent) return next(error);
    const status = error.code === 'LIMIT_FILE_SIZE' ? 413 : error.status || error.response?.status || 500;
    const message = error.code === 'LIMIT_FILE_SIZE' ? 'PDF must be 15MB or smaller' : status < 500 ? error.response?.data?.error || error.message : 'Service unavailable. Please try again.';
    if (status >= 500) console.error('Request failed', { path: req.path, code: error.code || 'internal' });
    res.status(status).json({ error: message });
  });
  return app;
}
if (require.main === module) {
  const { PrismaClient } = require('@prisma/client');
  const prisma = new PrismaClient();
  const app = createApp({ prisma });
  async function cleanup() {
    await prisma.analysis.deleteMany({ where: { expiresAt: { lte: new Date() } } });
    await prisma.cachedRecommendation.deleteMany({ where: { OR: [{ expiresAt: null }, { expiresAt: { lte: new Date() } }] } });
  }
  cleanup().catch(() => console.error('Retention cleanup failed'));
  const timer = setInterval(() => cleanup().catch(() => console.error('Retention cleanup failed')), 60000); timer.unref();
  const server = app.listen(Number(process.env.BACKEND_PORT || 3001));
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { clearInterval(timer); server.close(async () => { await prisma.$disconnect(); process.exit(0); }); });
}
module.exports = { createApp, configuration };
