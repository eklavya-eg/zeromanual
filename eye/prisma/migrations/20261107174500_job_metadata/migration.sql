BEGIN;

ALTER TABLE "worker_task_runs"
    ADD COLUMN "company_name" VARCHAR(500) NOT NULL DEFAULT 'NA',
    ADD COLUMN "job_title" VARCHAR(500) NOT NULL DEFAULT 'NA',
    ADD COLUMN "package" VARCHAR(500) NOT NULL DEFAULT 'NA',
    ADD COLUMN "platform" VARCHAR(160) NOT NULL DEFAULT 'NA';

ALTER TABLE "job_applications"
    ADD COLUMN "company_name" VARCHAR(500) NOT NULL DEFAULT 'NA',
    ADD COLUMN "job_title" VARCHAR(500) NOT NULL DEFAULT 'NA',
    ADD COLUMN "package" VARCHAR(500) NOT NULL DEFAULT 'NA',
    ADD COLUMN "platform" VARCHAR(160) NOT NULL DEFAULT 'NA';

-- Recover metadata already present in historical payloads without inventing pay.
UPDATE "worker_task_runs" SET
    "company_name" = CASE WHEN jsonb_typeof("payload" -> 'company_name') = 'string'
        THEN left(COALESCE(NULLIF(btrim("payload" ->> 'company_name'), ''), 'NA'), 500) ELSE 'NA' END,
    "job_title" = CASE WHEN jsonb_typeof("payload" -> 'job_title') = 'string'
        THEN left(COALESCE(NULLIF(btrim("payload" ->> 'job_title'), ''), 'NA'), 500) ELSE 'NA' END,
    "package" = CASE WHEN jsonb_typeof("payload" -> 'package') = 'string'
        AND lower(btrim("payload" ->> 'package')) NOT IN ('', 'na', 'n/a', 'not disclosed', 'not mentioned')
        THEN left(btrim("payload" ->> 'package'), 500) ELSE 'NA' END,
    "platform" = CASE
        WHEN jsonb_typeof("payload" -> 'platform') = 'string'
            AND lower(btrim("payload" ->> 'platform')) NOT IN ('', 'na', 'n/a', 'not disclosed', 'not mentioned')
            THEN left(btrim("payload" ->> 'platform'), 160)
        WHEN "job_url" ~* '^(https?://)?([a-z0-9-]+\.)*naukri\.com(:[0-9]+)?/' THEN 'Naukri'
        ELSE 'NA' END;

UPDATE "job_applications" AS job SET
    "company_name" = run."company_name",
    "job_title" = run."job_title",
    "package" = run."package",
    "platform" = run."platform"
FROM "worker_task_runs" AS run WHERE job."first_run_id" = run."id";

UPDATE "job_applications" SET "platform" = 'Naukri'
WHERE "platform" = 'NA' AND "job_url" ~* '^(https?://)?([a-z0-9-]+\.)*naukri\.com(:[0-9]+)?/';

COMMIT;
