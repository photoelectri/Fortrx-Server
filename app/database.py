from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

DATABASE_URL = settings.DATABASE_URL

if DATABASE_URL.startswith("postgresql+asyncpg"):
    sync_database_url = DATABASE_URL.replace("+asyncpg", "+psycopg2")
else:
    sync_database_url = DATABASE_URL

engine = create_engine(sync_database_url, echo=settings.SQL_ECHO, future=True)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def ensure_key_bundle_schema():
    inspector = inspect(engine)
    if not inspector.has_table("key_bundles"):
        return

    columns = {column["name"] for column in inspector.get_columns("key_bundles")}
    
    # We need to ensure all required columns exist
    required_columns = [
        ("user_id", "INTEGER"),
        ("identity_key", "TEXT"),
        ("signing_public", "TEXT"),
        ("signed_prekey", "TEXT"),
        ("signed_prekey_signature", "TEXT"),
        ("prekey_id", "INTEGER"),
        ("one_time_prekeys", "TEXT"),
        ("kyber_prekey_public", "TEXT"),
        ("kyber_prekey_signature", "TEXT"),
        ("updated_at", "DateTime")
    ]

    dialect = engine.dialect.name
    with engine.begin() as connection:
        for name, type_name in required_columns:
            if name not in columns:
                if dialect == "sqlite":
                    connection.execute(text(f"ALTER TABLE key_bundles ADD COLUMN {name} {type_name}"))
                else:
                    connection.execute(text(f"ALTER TABLE key_bundles ADD COLUMN IF NOT EXISTS {name} {type_name}"))


def ensure_server_changes_schema():
    inspector = inspect(engine)
    dialect = engine.dialect.name

    if inspector.has_table("users"):
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        user_additions = []
        if "backup_code_hash" not in user_columns:
            user_additions.append("backup_code_hash TEXT")
        if "backup_code_salt" not in user_columns:
            user_additions.append("backup_code_salt BYTEA" if dialect != "sqlite" else "backup_code_salt BLOB")
        if "backup_code_server_salt" not in user_columns:
            user_additions.append("backup_code_server_salt BYTEA" if dialect != "sqlite" else "backup_code_server_salt BLOB")
        if "backup_code_failures" not in user_columns:
            user_additions.append("backup_code_failures INTEGER NOT NULL DEFAULT 0")
        if "backup_code_locked_until" not in user_columns:
            user_additions.append("backup_code_locked_until BIGINT")
        if user_additions:
            with engine.begin() as connection:
                for addition in user_additions:
                    connection.execute(text(f"ALTER TABLE users ADD COLUMN {addition}"))

    if inspector.has_table("key_bundles"):
        bundle_columns = {column["name"] for column in inspector.get_columns("key_bundles")}
        bundle_additions = []
        if "device_id" not in bundle_columns:
            bundle_additions.append("device_id TEXT")
        if "identity_version" not in bundle_columns:
            bundle_additions.append("identity_version INTEGER NOT NULL DEFAULT 1")
        if "bundle_version" not in bundle_columns:
            bundle_additions.append("bundle_version INTEGER NOT NULL DEFAULT 1")
        if bundle_additions:
            with engine.begin() as connection:
                for addition in bundle_additions:
                    connection.execute(text(f"ALTER TABLE key_bundles ADD COLUMN {addition}"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
