from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from ..models.admin_audit_log import AdminAuditLog
from ..models.user import User

ADMIN_EMAIL = "hafiz.shadowfiend@gmail.com"


def is_admin_email(email: Optional[str]) -> bool:
    return " ".join(str(email or "").strip().lower().split()) == ADMIN_EMAIL


def log_audit_event(
    db: Session,
    *,
    user: Optional[User] = None,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> AdminAuditLog:
    row = AdminAuditLog(
        actor_user_id=getattr(user, "id", None),
        actor_email=(getattr(user, "email", None) or None),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details_json=json.dumps(details or {}, ensure_ascii=False),
    )
    db.add(row)
    return row
