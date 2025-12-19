import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from supabase import create_client, Client

from app.config import get_settings
from app.models import (
    Session, SessionCreate, SessionStatus,
    Event, EventCreate, EventType
)

logger = logging.getLogger(__name__)


class Database:
    _client: Optional[Client] = None
    _enabled: bool = True
    
    @classmethod
    def get_client(cls) -> Optional[Client]:
        if not cls._enabled:
            return None
            
        if cls._client is None:
            settings = get_settings()
            
            if not settings.supabase_url or not settings.supabase_key:
                logger.warning("Supabase not configured - database features disabled")
                cls._enabled = False
                return None
            
            if not settings.supabase_url.startswith("http"):
                logger.warning("Invalid Supabase URL - database features disabled")
                cls._enabled = False
                return None
            
            try:
                cls._client = create_client(
                    settings.supabase_url,
                    settings.supabase_key
                )
            except Exception as e:
                logger.error(f"Failed to create Supabase client: {e}")
                cls._enabled = False
                return None
                
        return cls._client
    
    @classmethod
    def is_enabled(cls) -> bool:
        return cls._enabled and cls.get_client() is not None
    
    @classmethod
    async def reset_client(cls):
        cls._client = None
        cls._enabled = True


async def create_session(session_data: SessionCreate) -> Optional[dict[str, Any]]:
    client = Database.get_client()
    if not client:
        from uuid import uuid4
        from datetime import datetime
        return {
            "id": str(uuid4()),
            "user_id": session_data.user_id,
            "status": SessionStatus.ACTIVE.value,
            "start_time": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    
    result = client.table("sessions").insert({
        "user_id": session_data.user_id,
        "status": SessionStatus.ACTIVE.value
    }).execute()
    
    if result.data:
        logger.info(f"Created session: {result.data[0]['id']}")
        return result.data[0]
    
    raise Exception("Failed to create session")


async def get_session(session_id: UUID) -> Optional[dict[str, Any]]:
    client = Database.get_client()
    if not client:
        return None
    
    result = client.table("sessions").select("*").eq(
        "id", str(session_id)
    ).execute()
    
    if result.data:
        return result.data[0]
    return None


async def update_session(
    session_id: UUID,
    updates: dict[str, Any]
) -> Optional[dict[str, Any]]:
    client = Database.get_client()
    if not client:
        return None
    
    result = client.table("sessions").update(updates).eq(
        "id", str(session_id)
    ).execute()
    
    if result.data:
        logger.info(f"Updated session: {session_id}")
        return result.data[0]
    return None


async def finalize_session(
    session_id: UUID,
    summary: str,
    end_time: datetime,
    duration_seconds: int
) -> Optional[dict[str, Any]]:
    return await update_session(session_id, {
        "summary": summary,
        "end_time": end_time.isoformat(),
        "duration_seconds": duration_seconds,
        "status": SessionStatus.COMPLETED.value
    })


async def delete_session(session_id: UUID) -> bool:
    client = Database.get_client()
    if not client:
        return False
    
    try:
        client.table("events").delete().eq(
            "session_id", str(session_id)
        ).execute()
        
        result = client.table("sessions").delete().eq(
            "id", str(session_id)
        ).execute()
        
        if result.data:
            logger.info(f"Deleted session: {session_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        return False


async def get_session_message_count(session_id: UUID) -> int:
    client = Database.get_client()
    if not client:
        return 0
    
    try:
        result = client.table("events").select("id", count="exact").eq(
            "session_id", str(session_id)
        ).eq(
            "event_type", EventType.USER_MESSAGE.value
        ).execute()
        
        return result.count or 0
    except Exception as e:
        logger.error(f"Failed to get message count for session {session_id}: {e}")
        return 0


async def get_first_user_message(session_id: UUID) -> Optional[str]:
    client = Database.get_client()
    if not client:
        return None
    
    try:
        result = client.table("events").select("content").eq(
            "session_id", str(session_id)
        ).eq(
            "event_type", EventType.USER_MESSAGE.value
        ).order("timestamp", desc=False).limit(1).execute()
        
        if result.data:
            return result.data[0].get("content")
        return None
    except Exception as e:
        logger.error(f"Failed to get first message for session {session_id}: {e}")
        return None


async def cleanup_empty_sessions() -> int:
    client = Database.get_client()
    if not client:
        return 0
    
    deleted_count = 0
    
    try:
        result = client.table("sessions").select("id").is_(
            "end_time", "null"
        ).execute()
        
        if not result.data:
            return 0
        
        for session in result.data:
            session_id = session["id"]
            
            msg_result = client.table("events").select("id", count="exact").eq(
                "session_id", session_id
            ).eq(
                "event_type", EventType.USER_MESSAGE.value
            ).execute()
            
            message_count = msg_result.count or 0
            
            if message_count == 0:
                client.table("events").delete().eq(
                    "session_id", session_id
                ).execute()
                
                client.table("sessions").delete().eq(
                    "id", session_id
                ).execute()
                
                deleted_count += 1
                logger.info(f"Cleaned up empty session: {session_id}")
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} empty sessions")
        
        return deleted_count
        
    except Exception as e:
        logger.error(f"Failed to cleanup empty sessions: {e}")
        return deleted_count


async def create_event(event_data: EventCreate) -> Optional[dict[str, Any]]:
    client = Database.get_client()
    if not client:
        from uuid import uuid4
        return {
            "id": str(uuid4()),
            "session_id": str(event_data.session_id),
            "event_type": event_data.event_type.value,
            "content": event_data.content,
            "metadata": event_data.metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }
    
    result = client.table("events").insert({
        "session_id": str(event_data.session_id),
        "event_type": event_data.event_type.value,
        "content": event_data.content,
        "metadata": event_data.metadata or {}
    }).execute()
    
    if result.data:
        logger.debug(f"Created event: {result.data[0]['id']}")
        return result.data[0]
    
    raise Exception("Failed to create event")


async def get_session_events(
    session_id: UUID,
    event_types: Optional[list[EventType]] = None
) -> list[dict[str, Any]]:
    client = Database.get_client()
    if not client:
        return []
    
    query = client.table("events").select("*").eq(
        "session_id", str(session_id)
    ).order("timestamp", desc=False)
    
    if event_types:
        type_values = [et.value for et in event_types]
        query = query.in_("event_type", type_values)
    
    result = query.execute()
    return result.data or []


async def get_conversation_history(session_id: UUID) -> list[dict[str, Any]]:
    return await get_session_events(
        session_id,
        event_types=[EventType.USER_MESSAGE, EventType.AI_RESPONSE]
    )


async def log_user_message(session_id: UUID, content: str) -> dict[str, Any]:
    return await create_event(EventCreate(
        session_id=session_id,
        event_type=EventType.USER_MESSAGE,
        content=content
    ))


async def log_ai_response(
    session_id: UUID,
    content: str,
    metadata: Optional[dict] = None
) -> dict[str, Any]:
    return await create_event(EventCreate(
        session_id=session_id,
        event_type=EventType.AI_RESPONSE,
        content=content,
        metadata=metadata
    ))


async def log_tool_call(
    session_id: UUID,
    tool_name: str,
    tool_input: dict
) -> dict[str, Any]:
    return await create_event(EventCreate(
        session_id=session_id,
        event_type=EventType.TOOL_CALL,
        content=f"Called tool: {tool_name}",
        metadata={"tool_name": tool_name, "input": tool_input}
    ))


async def log_tool_result(
    session_id: UUID,
    tool_name: str,
    result: Any
) -> dict[str, Any]:
    return await create_event(EventCreate(
        session_id=session_id,
        event_type=EventType.TOOL_RESULT,
        content=f"Tool result from: {tool_name}",
        metadata={"tool_name": tool_name, "result": result}
    ))


async def log_system_event(
    session_id: UUID,
    content: str,
    metadata: Optional[dict] = None
) -> dict[str, Any]:
    return await create_event(EventCreate(
        session_id=session_id,
        event_type=EventType.SYSTEM,
        content=content,
        metadata=metadata
    ))


async def log_error(
    session_id: UUID,
    error_message: str,
    metadata: Optional[dict] = None
) -> dict[str, Any]:
    return await create_event(EventCreate(
        session_id=session_id,
        event_type=EventType.ERROR,
        content=error_message,
        metadata=metadata
    ))
