const express = require("express");
const axios = require("axios");
const cors = require("cors");
const multer = require("multer");
const FormData = require("form-data");
const helmet = require("helmet");
const rateLimit = require("express-rate-limit");
const crypto = require("crypto");
const bcrypt = require("bcryptjs");
const jwt = require("jsonwebtoken");
const { PrismaClient } = require("@prisma/client");
require("dotenv").config();

const app = express();
app.set("trust proxy", 1);
const prisma = new PrismaClient();

const allowedOrigins = (process.env.ALLOWED_ORIGINS || "http://localhost:3000,http://localhost:3001")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 15 * 1024 * 1024,
  },
  fileFilter: (req, file, cb) => {
    if (file.mimetype !== "application/pdf") {
      return cb(new Error("Only PDF files are allowed"));
    }

    cb(null, true);
  },
});
const FLASK_API_URL = process.env.FLASK_API_URL;
const PORT = Number(process.env.BACKEND_PORT || process.env.PORT);
const JWT_SECRET = process.env.JWT_SECRET;
const GUEST_ANALYZE_LIMIT = Number(process.env.GUEST_ANALYZE_LIMIT || 2);

if (!FLASK_API_URL) {
  throw new Error("Missing FLASK_API_URL in backend environment");
}

if (!PORT) {
  throw new Error("Missing BACKEND_PORT in backend environment");
}

if (!JWT_SECRET) {
  throw new Error("Missing JWT_SECRET in backend environment");
}

app.use(helmet());
app.use(
  cors({
    origin: (origin, callback) => {
      if (!origin || allowedOrigins.includes(origin)) {
        return callback(null, true);
      }

      return callback(new Error("CORS origin not allowed"));
    },
    methods: ["GET", "POST", "OPTIONS"],
  })
);
// Rate limit only expensive/abusable endpoints.
// Polling (/api/status/:jobId) is intentionally excluded because it is frequent/low-cost.
const apiRateLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 1000,
  standardHeaders: true,
  legacyHeaders: false,
});

app.use(express.json({ limit: "10mb" }));

app.post('/api/analyze', apiRateLimiter);
app.post('/api/recommend', apiRateLimiter);

const getAuthenticatedUser = async (req) => {
  const header = req.headers.authorization || "";
  if (!header.startsWith("Bearer ")) return null;

  try {
    const payload = jwt.verify(header.slice(7), JWT_SECRET);
    return prisma.user.findUnique({ where: { id: payload.sub } });
  } catch (_error) {
    return null;
  }
};

const normalizeIp = (value) => String(value || "unknown").replace("::ffff:", "").trim() || "unknown";

const getClientIp = (req) => {
  const forwarded = req.headers["x-forwarded-for"];
  if (typeof forwarded === "string" && forwarded.length > 0) {
    return normalizeIp(forwarded.split(",")[0]);
  }

  return normalizeIp(req.ip || req.socket?.remoteAddress);
};

const getGuestAnalyzeUsage = async (ip) => {
  const record = await prisma.guestUsage.findUnique({ where: { ip } });
  return record?.analysesUsed || 0;
};

const incrementGuestAnalyzeUsage = async (ip) => {
  const record = await prisma.guestUsage.upsert({
    where: { ip },
    update: { analysesUsed: { increment: 1 } },
    create: { ip, analysesUsed: 1 },
  });
  return record.analysesUsed;
};

app.post("/api/auth/register", apiRateLimiter, async (req, res) => {
  const email = String(req.body?.email || "").trim().toLowerCase();
  const password = String(req.body?.password || "");
  const name = String(req.body?.name || "").trim() || null;

  if (!/^\S+@\S+\.\S+$/.test(email) || password.length < 10) {
    return res.status(400).json({ error: "Valid email and password of at least 10 characters are required" });
  }

  try {
    const passwordHash = await bcrypt.hash(password, 12);
    const user = await prisma.user.create({ data: { email, name, passwordHash } });
    const token = jwt.sign({ sub: user.id, email: user.email }, JWT_SECRET, { expiresIn: "7d" });
    return res.status(201).json({ token, user: { id: user.id, email: user.email, name: user.name } });
  } catch (error) {
    if (error.code === "P2002") return res.status(409).json({ error: "Email is already registered" });
    console.error("Registration error:", error.message);
    return res.status(500).json({ error: "Failed to register" });
  }
});

app.post("/api/auth/login", apiRateLimiter, async (req, res) => {
  const email = String(req.body?.email || "").trim().toLowerCase();
  const password = String(req.body?.password || "");
  const user = await prisma.user.findUnique({ where: { email } });
  const valid = user?.passwordHash && await bcrypt.compare(password, user.passwordHash);

  if (!valid) return res.status(401).json({ error: "Invalid email or password" });
  const token = jwt.sign({ sub: user.id, email: user.email }, JWT_SECRET, { expiresIn: "7d" });
  return res.json({ token, user: { id: user.id, email: user.email, name: user.name } });
});


const validateRecommendationBody = (body) => {
  if (!body || typeof body !== "object") {
    return "Request body is required";
  }

  if (body.paper_text && typeof body.paper_text !== "string") {
    return "paper_text must be a string";
  }

  if (body.paper_topic && typeof body.paper_topic !== "string") {
    return "paper_topic must be a string";
  }

  if (body.paper_score !== undefined && Number.isNaN(Number(body.paper_score))) {
    return "paper_score must be numeric";
  }

  return null;
};

const hashValue = (value) =>
  crypto.createHash("sha256").update(typeof value === "string" ? value : JSON.stringify(value || {})).digest("hex");

const persistAnalysis = async (jobId, fileName, responseData, userId = null) => {
  try {
    if (!jobId) {
      return;
    }

    await prisma.analysis.upsert({
      where: { jobId },
      update: {
        userId,
        paperFilename: fileName || "unknown.pdf",
        extractedScore: Number(responseData?.score || 0),
        features: responseData?.features || {},
        summary: responseData?.summary || "",
      },
      create: {
        jobId,
        userId,
        paperFilename: fileName || "unknown.pdf",
        extractedScore: Number(responseData?.score || 0),
        features: responseData?.features || {},
        summary: responseData?.summary || "",
      },
    });
  } catch (error) {
    console.error("Failed to persist analysis:", error.message);
  }
};

const persistRecommendation = async (requestBody, responseData, userId = null) => {
  try {
    const paperText = requestBody?.paper_text || "";
    const preferences = {
      paper_score: requestBody?.paper_score,
      paper_topic: requestBody?.paper_topic,
      venue_type: requestBody?.venue_type,
      open_access_only: requestBody?.open_access_only,
      exclude_discontinued: requestBody?.exclude_discontinued,
      medline_only: requestBody?.medline_only,
      min_coverage_year: requestBody?.min_coverage_year,
      selected_subjects: requestBody?.selected_subjects,
      indexing: requestBody?.indexing,
      fee_pref: requestBody?.fee_pref,
      acceptance: requestBody?.acceptance,
      publisher: requestBody?.publisher,
    };
    const paperHash = hashValue(paperText);
    const preferencesHash = hashValue(preferences);
    const cacheKey = `${paperHash}:${preferencesHash}`;
    const storedRequestPayload = { ...requestBody };
    delete storedRequestPayload.paper_text;
    storedRequestPayload.paper_text_redacted = true;

    await prisma.cachedRecommendation.upsert({
      where: { cacheKey },
      update: {
        userId,
        paperHash,
        preferencesHash,
        requestPayload: storedRequestPayload,
        result: responseData,
      },
      create: {
        cacheKey,
        userId,
        paperHash,
        preferencesHash,
        requestPayload: storedRequestPayload,
        result: responseData,
      },
    });
  } catch (error) {
    console.error("Failed to persist recommendation:", error.message);
  }
};

app.post("/api/analyze", upload.single("file"), async (req, res) => {
  try {
    const user = await getAuthenticatedUser(req);
    const isGuest = !user;
    const guestIp = isGuest ? getClientIp(req) : null;

  if (isGuest && (await getGuestAnalyzeUsage(guestIp)) >= GUEST_ANALYZE_LIMIT) {
      return res.status(403).json({
        error: `Guest usage limit reached. You can analyze ${GUEST_ANALYZE_LIMIT} papers without login. Please sign in to continue.`,
        requiresAuth: true,
        guestLimit: GUEST_ANALYZE_LIMIT,
      });
    }

    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded" });
    }

    const formData = new FormData();
    formData.append("file", req.file.buffer, "file.pdf");

    const response = await axios.post(
      `${FLASK_API_URL}/analyze`,
      formData,
      {
        headers: {
          ...formData.getHeaders(),
        },
        timeout: 120000,
      }
    );

    // Flask /analyze returns { job_id, status, status_url }
    if (isGuest && guestIp) {
      const used = await incrementGuestAnalyzeUsage(guestIp);
      res.set("X-Guest-Analyses-Used", String(used));
      res.set("X-Guest-Analyses-Limit", String(GUEST_ANALYZE_LIMIT));
    }

    res.json(response.data);

  } catch (error) {
    const status = error.response?.status || 500;
    const message = error.response?.data?.error || error.message || "Error processing file";
    console.error("Analyze error:", message);
    res.status(status).json({ error: message });
  }
});

app.get("/api/status/:jobId", async (req, res) => {
  res.set("Cache-Control", "no-store");
  try {
    const response = await axios.get(`${FLASK_API_URL}/status/${req.params.jobId}`, {
      timeout: 120000,
    });

    if (response.data?.status === "finished" && response.data?.result) {
      const user = await getAuthenticatedUser(req);
      void persistAnalysis(response.data.job_id, response.data.file_name, response.data.result, user?.id);
    }

    res.json(response.data);
  } catch (error) {
    const status = error.response?.status || 500;
    const message = error.response?.data?.error || error.message || "Error checking job status";
    console.error("Status error:", message);
    res.status(status).json({ error: message });
  }
});

app.post("/api/recommend", async (req, res) => {
  try {
    const validationError = validateRecommendationBody(req.body);
    if (validationError) {
      return res.status(400).json({ error: validationError });
    }

    const response = await axios.post(`${FLASK_API_URL}/recommend`, req.body, {
      timeout: 120000,
    });

    res.json(response.data);
    const user = await getAuthenticatedUser(req);
    void persistRecommendation(req.body, response.data, user?.id);
  } catch (error) {
    const status = error.response?.status || 500;
    const message = error.response?.data?.error || error.message || "Error fetching recommendations";
    console.error("Recommend error:", message);
    res.status(status).json({ error: message });
  }
});

app.use((error, req, res, next) => {
  if (error && error.message === "Only PDF files are allowed") {
    return res.status(400).json({ error: error.message });
  }

  if (error && error.code === "LIMIT_FILE_SIZE") {
    return res.status(413).json({ error: "PDF file must be 15MB or smaller" });
  }

  return next(error);
});

app.use((err, req, res, next) => {
  console.error("Unhandled server error:", err);
  res.status(500).json({ error: "Internal server error" });
});

app.get("/api/history", async (req, res) => {
  try {
    const limit = Math.min(Number(req.query.limit || 25), 100);
    const user = await getAuthenticatedUser(req);
    const history = await prisma.analysis.findMany({
      where: user ? { userId: user.id } : { userId: null },
      orderBy: { createdAt: "desc" },
      take: limit,
    });

    res.json({ history });
  } catch (error) {
    console.error("History error:", error.message);
    res.status(500).json({ error: "Failed to load history" });
  }
});

process.on("SIGINT", async () => {
  await prisma.$disconnect();
  process.exit(0);
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});