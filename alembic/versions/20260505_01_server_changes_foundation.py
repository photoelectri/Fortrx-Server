"""server changes foundation

Revision ID: 20260505_01
Revises:
Create Date: 2026-05-05

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260505_01"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # --- 1. Initial Table Creation ---
    # These tables must exist before we can alter them or reference them in foreign keys.
    op.create_table(
        "users", 
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True), 
        sa.Column("username", sa.String(), unique=True, nullable=False), 
        sa.Column("email", sa.String(), unique=True, nullable=False), 
        sa.Column("hashed_password", sa.String(), nullable=False), 
        sa.Column("identity_public_key", sa.String(), nullable=True), 
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()), 
        sa.Column("is_active", sa.Boolean(), default=True)
    )
    
    op.create_table(
        "key_bundles", 
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("identity_key", sa.Text(), nullable=True),
        sa.Column("signing_public", sa.Text(), nullable=True),
        sa.Column("signed_prekey", sa.Text(), nullable=True),
        sa.Column("signed_prekey_signature", sa.Text(), nullable=True),
        sa.Column("prekey_id", sa.Integer(), nullable=True),
        sa.Column("one_time_prekeys", sa.Text(), nullable=True),
        sa.Column("device_id", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("kyber_prekey_public", sa.Text(), nullable=True),
        sa.Column("kyber_prekey_signature", sa.Text(), nullable=True),
    )
    op.create_index("ix_key_bundles_user_id", "key_bundles", ["user_id"])
    op.create_index("ix_key_bundles_device_id", "key_bundles", ["device_id"])

    # --- 2. Alterations (Adding new columns to existing tables) ---
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("backup_code_hash", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("backup_code_salt", sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column("backup_code_server_salt", sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column("backup_code_failures", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("backup_code_locked_until", sa.BigInteger(), nullable=True))

    # --- 3. Creation of Dependent Tables ---
    op.create_table(
        "devices",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("identity_pub", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("last_seen", sa.BigInteger(), nullable=False),
        sa.Column("revoked_at", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.String(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=True),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("revoked_at", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_device_id", "refresh_tokens", ["device_id"])

    op.create_table(
        "pairing_codes",
        sa.Column("code_hash", sa.LargeBinary(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("used_at", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_pairing_codes_user_id", "pairing_codes", ["user_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor", sa.Integer(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("ts", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_audit_log_actor", "audit_log", ["actor"])

    op.create_table(
        "action_tokens",
        sa.Column("jti", sa.String(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("token_type", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=True),
        sa.Column("device_id", sa.String(), nullable=True),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("used_at", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_action_tokens_user_id", "action_tokens", ["user_id"])

def downgrade() -> None:
    op.drop_index("ix_action_tokens_user_id", table_name="action_tokens")
    op.drop_table("action_tokens")
    op.drop_index("ix_audit_log_actor", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_pairing_codes_user_id", table_name="pairing_codes")
    op.drop_table("pairing_codes")
    op.drop_index("ix_refresh_tokens_device_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_devices_user_id", table_name="devices")
    op.drop_table("devices")
    
    with op.batch_alter_table("key_bundles") as batch_op:
        batch_op.drop_column("device_id")
    
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("backup_code_locked_until")
        batch_op.drop_column("backup_code_failures")
        batch_op.drop_column("backup_code_server_salt")
        batch_op.drop_column("backup_code_salt")
        batch_op.drop_column("backup_code_hash")
    
    op.drop_table("key_bundles")
    op.drop_table("users")
