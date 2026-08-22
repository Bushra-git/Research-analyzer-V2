-- Add domain metadata for balanced cross-domain OpenAlex seeding.
ALTER TABLE "reference_papers"
    ADD COLUMN "research_domain" TEXT NOT NULL DEFAULT 'General';

CREATE INDEX "reference_papers_research_domain_idx"
    ON "reference_papers"("research_domain");