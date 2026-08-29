"""Initial schema migration.

Creates all tables from the SQLAlchemy metadata. Subsequent schema changes are
added as new revision files so production Postgres deployments can be migrated
incrementally (rather than relying on ``create_all`` which cannot alter tables).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from src.naukri_agent.models.db_schema import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


async def upgrade() -> None:
    bind = op.get_bind()
    await bind.run_sync(lambda conn: Base.metadata.create_all(conn))


async def downgrade() -> None:
    bind = op.get_bind()
    await bind.run_sync(lambda conn: Base.metadata.drop_all(conn))
