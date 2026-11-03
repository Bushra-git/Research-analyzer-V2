ALTER TABLE "Analysis" ALTER COLUMN "extractedScore" DROP NOT NULL;
ALTER TABLE "Analysis" ADD COLUMN "ownerKey" TEXT;
ALTER TABLE "Analysis" ADD COLUMN "status" TEXT NOT NULL DEFAULT 'queued';
ALTER TABLE "Analysis" ADD COLUMN "result" JSONB;
ALTER TABLE "Analysis" ADD COLUMN "expiresAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;
-- Legacy records have no verifiable guest ownership. Expire rather than exposing them.
CREATE INDEX "Analysis_ownerKey_createdAt_idx" ON "Analysis"("ownerKey", "createdAt");
CREATE INDEX "Analysis_expiresAt_idx" ON "Analysis"("expiresAt");
