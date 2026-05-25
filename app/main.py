import asyncio
import logging
from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware
from slowapi import _rate_limit_exceeded_handler
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from app.database import Base,engine,SessionLocal,ensure_key_bundle_schema, ensure_server_changes_schema
from app.config import settings
import app.models,app.schemas,app.services
from app.routers import account, attachments, auth, devices, keys, messages, ws, safety, presence
from app.services import ensure_bucket_exists,purge_expired_attachments,purge_expired_messages
from app.middleware import limiter,SecurityHeadersMiddleware


class HealthcheckAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = getattr(record, "args", ())
        if not isinstance(args, tuple) or len(args) < 3:
            return True
        path = args[2]
        return path != "/healthz"

async def expired_message_cleanup():
    print("Background cleanup worker started.")
    while True:
        await asyncio.sleep(60)
        db = SessionLocal()
        try:
            deleted_count = purge_expired_messages(db)
            deleted_attachments = purge_expired_attachments(db)
            if deleted_count > 0:
                print(f"Purged {deleted_count} expired messages.")
            if deleted_attachments > 0:
                print(f"Purged {deleted_attachments} expired attachments.")
        except Exception as e:
            db.rollback()  
            print(f"Cleanup error: {e}")
        finally:
            db.close()
@asynccontextmanager
async def lifespan(app: FastAPI):
    #Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ensure_key_bundle_schema()
    ensure_server_changes_schema()
    ensure_bucket_exists()
    cleanup_task = asyncio.create_task(expired_message_cleanup())
    yield
    cleanup_task.cancel()

app = FastAPI(title='Fortrx', lifespan=lifespan)
app.include_router(keys.router)
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(account.router)
app.include_router(attachments.router)
app.include_router(messages.router)
app.include_router(ws.router)
app.include_router(safety.router)
app.include_router(presence.router)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded,_rate_limit_exceeded_handler)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(SecurityHeadersMiddleware)
logging.getLogger("uvicorn.access").addFilter(HealthcheckAccessFilter())

@app.get('/')
async def health():
    return {
        "status":"Fortrx is running",
        "public_base_url": settings.PUBLIC_BASE_URL,
    }


@app.get('/healthz')
async def healthz():
    return {
        "status":"Fortrx is running",
        "deploy_env": settings.DEPLOY_ENV,
    }


# docker run -d --name localstack -p 4566:4566 localstack/localstac
# docker run -d --name minio -p 4566:4566 quay.io/minio/minio server /data --address ":4566"
# docker run -p 6379:6379 redis:alpine
