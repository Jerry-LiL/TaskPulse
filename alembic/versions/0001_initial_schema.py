"""Initial schema with composite indexes

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-10-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. schedules table
    op.create_table(
        "schedules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("cron_expression", sa.String(length=100), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_schedules_user_id", "schedules", ["user_id"])
    # Composite indexes for schedules
    op.create_index("ix_schedules_user_active", "schedules", ["user_id", "is_active"])
    op.create_index("ix_schedules_active_next_run", "schedules", ["is_active", "next_run_at"])

    # 3. jobs table
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("schedule_id", sa.String(length=36), nullable=True),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_index("ix_jobs_schedule_id", "jobs", ["schedule_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    # Composite indexes for jobs
    op.create_index("ix_jobs_user_status", "jobs", ["user_id", "status"])
    op.create_index("ix_jobs_user_created", "jobs", ["user_id", "created_at"])
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])

    # 4. webhooks table
    op.create_table(
        "webhooks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("secret", sa.String(length=128), nullable=False),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhooks_user_id", "webhooks", ["user_id"])
    # Composite indexes for webhooks
    op.create_index("ix_webhooks_user_active", "webhooks", ["user_id", "is_active"])

    # 5. webhook_deliveries table
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("webhook_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("event", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["webhook_id"], ["webhooks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_deliveries_webhook_id", "webhook_deliveries", ["webhook_id"])
    op.create_index("ix_webhook_deliveries_job_id", "webhook_deliveries", ["job_id"])
    # Composite indexes for webhook deliveries
    op.create_index(
        "ix_webhook_deliveries_webhook_created",
        "webhook_deliveries",
        ["webhook_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_webhook_created", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_job_id", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_webhook_id", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")

    op.drop_index("ix_webhooks_user_active", table_name="webhooks")
    op.drop_index("ix_webhooks_user_id", table_name="webhooks")
    op.drop_table("webhooks")

    op.drop_index("ix_jobs_status_created", table_name="jobs")
    op.drop_index("ix_jobs_user_created", table_name="jobs")
    op.drop_index("ix_jobs_user_status", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_schedule_id", table_name="jobs")
    op.drop_index("ix_jobs_user_id", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_schedules_active_next_run", table_name="schedules")
    op.drop_index("ix_schedules_user_active", table_name="schedules")
    op.drop_index("ix_schedules_user_id", table_name="schedules")
    op.drop_table("schedules")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
