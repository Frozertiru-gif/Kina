from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent


async def log_audit_event(
    session: AsyncSession,
    *,
    actor_type: str,
    actor_user_id: int | None,
    actor_admin_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    event = AuditEvent(
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        actor_admin_id=actor_admin_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=metadata_json,
    )
    session.add(event)
