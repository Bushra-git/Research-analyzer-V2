-- CreateTable
CREATE TABLE "reference_papers" (
    "id" BIGSERIAL NOT NULL,
    "openalex_id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "abstract" TEXT NOT NULL,
    "authors" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "venue_name" TEXT,
    "venue_type" TEXT,
    "venue_issn" TEXT,
    "publication_year" INTEGER,
    "citation_count" INTEGER NOT NULL DEFAULT 0,
    "text_content" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "reference_papers_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "reference_papers_openalex_id_key"
    ON "reference_papers"("openalex_id");

-- CreateIndex
CREATE INDEX "reference_papers_publication_year_idx"
    ON "reference_papers"("publication_year");

-- CreateIndex
CREATE INDEX "reference_papers_citation_count_idx"
    ON "reference_papers"("citation_count");
