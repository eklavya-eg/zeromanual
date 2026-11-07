CREATE TABLE "job_applications" (
    "job_url" VARCHAR(2048) NOT NULL,
    "first_run_id" UUID,
    "status" VARCHAR(20) NOT NULL DEFAULT 'running',
    "reason" TEXT,
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "modified_at" TIMESTAMPTZ(6) NOT NULL,
    CONSTRAINT "job_applications_pkey" PRIMARY KEY ("job_url")
);
CREATE UNIQUE INDEX "job_applications_first_run_id_key" ON "job_applications"("first_run_id");
ALTER TABLE "job_applications" ADD CONSTRAINT "job_applications_first_run_id_fkey" FOREIGN KEY ("first_run_id") REFERENCES "worker_task_runs"("id") ON DELETE SET NULL ON UPDATE CASCADE;

CREATE TABLE "worker_skips" (
    "id" UUID NOT NULL,
    "task_run_id" UUID NOT NULL,
    "job_url" VARCHAR(2048) NOT NULL,
    "reason" VARCHAR(30) NOT NULL,
    "details" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "worker_skips_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "worker_skips_task_run_id_key" ON "worker_skips"("task_run_id");
CREATE INDEX "worker_skips_job_url_idx" ON "worker_skips"("job_url");
CREATE INDEX "worker_skips_reason_idx" ON "worker_skips"("reason");
ALTER TABLE "worker_skips" ADD CONSTRAINT "worker_skips_task_run_id_fkey" FOREIGN KEY ("task_run_id") REFERENCES "worker_task_runs"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Preserve history, but replace the stored URL (including its payload copy) with domain/path.
WITH parts AS (
    SELECT "id", split_part(split_part(regexp_replace("job_url", '^https?://', '', 'i'), '?', 1), '#', 1) AS url
    FROM "worker_task_runs"
), normalized AS (
    SELECT "id", regexp_replace(lower(split_part(url, '/', 1)), ':(80|443)$', '') ||
        CASE WHEN position('/' in url) > 0 THEN substring(url FROM position('/' in url)) ELSE '/' END AS url
    FROM parts
)
UPDATE "worker_task_runs" AS run SET "job_url" = normalized.url,
    "payload" = jsonb_set(run."payload", '{job_url}', to_jsonb(normalized.url), true)
FROM normalized WHERE run."id" = normalized."id";

-- Backfill one identity for previously seen application jobs, including failed attempts.
INSERT INTO "job_applications" ("job_url", "first_run_id", "status", "created_at", "modified_at")
SELECT DISTINCT ON ("job_url") "job_url", "id", "status", "started_at", CURRENT_TIMESTAMP
FROM "worker_task_runs"
ORDER BY "job_url", "started_at", "id";
