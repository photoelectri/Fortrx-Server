"""auth pairing bundle version updates

Revision ID: 20260510_02
Revises: 20260505_01
Create Date: 2026-05-10

"""

from alembic import op
import sqlalchemy as sa


revision = "20260510_02"
down_revision = "20260505_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("key_bundles") as batch_op:
        batch_op.add_column(sa.Column("identity_version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("bundle_version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("key_bundles") as batch_op:
        batch_op.drop_column("bundle_version")
        batch_op.drop_column("identity_version")
