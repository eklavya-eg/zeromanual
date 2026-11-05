-- CreateTable
CREATE TABLE "workers" (
    "id" UUID NOT NULL,
    "name" VARCHAR(160) NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "modified_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "workers_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "worker_task_runs" (
    "id" UUID NOT NULL,
    "worker_id" UUID NOT NULL,
    "celery_task_id" VARCHAR(160) NOT NULL,
    "job_url" VARCHAR(2048) NOT NULL,
    "payload" JSONB NOT NULL,
    "result" JSONB,
    "status" VARCHAR(20) NOT NULL,
    "started" BOOLEAN NOT NULL DEFAULT true,
    "success" BOOLEAN NOT NULL DEFAULT false,
    "failed" BOOLEAN NOT NULL DEFAULT false,
    "step_failed" VARCHAR(120),
    "error" TEXT,
    "started_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finished_at" TIMESTAMPTZ(6),

    CONSTRAINT "worker_task_runs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "worker_logs" (
    "id" UUID NOT NULL,
    "worker_id" UUID NOT NULL,
    "task_run_id" UUID NOT NULL,
    "level" VARCHAR(20) NOT NULL,
    "step" VARCHAR(120) NOT NULL,
    "message" TEXT NOT NULL,
    "details" JSONB,
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "worker_logs_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "workers_name_key" ON "workers"("name");
CREATE UNIQUE INDEX "worker_task_runs_celery_task_id_key" ON "worker_task_runs"("celery_task_id");
CREATE INDEX "worker_task_runs_worker_id_idx" ON "worker_task_runs"("worker_id");
CREATE INDEX "worker_task_runs_status_idx" ON "worker_task_runs"("status");
CREATE INDEX "worker_task_runs_started_at_idx" ON "worker_task_runs"("started_at");
CREATE INDEX "worker_logs_worker_id_idx" ON "worker_logs"("worker_id");
CREATE INDEX "worker_logs_task_run_id_idx" ON "worker_logs"("task_run_id");
CREATE INDEX "worker_logs_created_at_idx" ON "worker_logs"("created_at");

-- AddForeignKey
ALTER TABLE "worker_task_runs" ADD CONSTRAINT "worker_task_runs_worker_id_fkey" FOREIGN KEY ("worker_id") REFERENCES "workers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "worker_logs" ADD CONSTRAINT "worker_logs_worker_id_fkey" FOREIGN KEY ("worker_id") REFERENCES "workers"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "worker_logs" ADD CONSTRAINT "worker_logs_task_run_id_fkey" FOREIGN KEY ("task_run_id") REFERENCES "worker_task_runs"("id") ON DELETE CASCADE ON UPDATE CASCADE;
