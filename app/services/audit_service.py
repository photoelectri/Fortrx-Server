from sqlalchemy.orm import Session

from app.models import AuditLog
from app.services.auth_service import now_ms


def write_audit_log(
    db: Session,
    actor: int | None,
    action: str,
    meta: dict | None = None,
    commit: bool = False,
) -> AuditLog:
    row = AuditLog(actor=actor, action=action, meta=meta, ts=now_ms())
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    return row
