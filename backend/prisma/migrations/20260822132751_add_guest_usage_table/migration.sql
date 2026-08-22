-- DropIndex
DROP INDEX "reference_papers_research_domain_idx";

-- AlterTable
ALTER TABLE "reference_papers" ALTER COLUMN "updated_at" DROP DEFAULT,
ALTER COLUMN "research_domain" DROP DEFAULT;

-- CreateTable
CREATE TABLE "guest_usage" (
    "ip" TEXT NOT NULL,
    "analyses_used" INTEGER NOT NULL DEFAULT 0,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "guest_usage_pkey" PRIMARY KEY ("ip")
);
