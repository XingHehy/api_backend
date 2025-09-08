import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.admin import models as admin_models

logger = logging.getLogger(__name__)

def log_action(
    db: Session,
    *,
    actor_id: Optional[int] = None,
    actor_type: str = "system",
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    description: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Optional[int]:
    """写入系统操作日志。

    返回新日志ID，异常时返回None（不影响主流程）。
    """
    try:
        system_log = admin_models.SystemLog(
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            meta=metadata,
            ip=ip,
            user_agent=user_agent
        )
        db.add(system_log)
        db.commit()
        db.refresh(system_log)
        return system_log.id
    except Exception as e:
        logger.error(f"写入系统日志失败: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None


