CREATE TYPE "WorkflowStepType" AS ENUM ('sub_agent', 'command');

ALTER TABLE "workflow_steps"
    ADD COLUMN "step_type" "WorkflowStepType" NOT NULL DEFAULT 'sub_agent',
    ADD COLUMN "command" TEXT,
    ADD COLUMN "working_directory" TEXT,
    ADD COLUMN "timeout_seconds" INTEGER NOT NULL DEFAULT 300,
    ALTER COLUMN "sub_agent_id" DROP NOT NULL;

ALTER TABLE "workflow_steps" ADD CONSTRAINT "workflow_steps_type_fields_check" CHECK (
    ("step_type" = 'sub_agent' AND "sub_agent_id" IS NOT NULL AND "command" IS NULL AND "working_directory" IS NULL)
    OR
    ("step_type" = 'command' AND "sub_agent_id" IS NULL AND "command" IS NOT NULL AND length(trim("command")) > 0)
);
ALTER TABLE "workflow_steps" ADD CONSTRAINT "workflow_steps_timeout_check"
    CHECK ("timeout_seconds" BETWEEN 1 AND 86400);
