import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from app.database import (
    create_session, get_session, update_session,
    log_user_message, log_ai_response, log_tool_call,
    log_tool_result, log_system_event, log_error
)
from app.models import SessionCreate, SessionStatus

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, session_id: UUID, user_id: str = "anonymous"):
        self.session_id = session_id
        self.user_id = user_id
        self.start_time: Optional[datetime] = None
        self.is_active = False
    
    async def start_session(self) -> dict[str, Any]:
        self.start_time = datetime.utcnow()
        
        try:
            session_data = SessionCreate(user_id=self.user_id)
            session = await create_session(session_data)
            
            self.session_id = UUID(session["id"])
            self.is_active = True
            
            logger.info(f"Session started: {self.session_id}")
            return session
            
        except Exception as e:
            logger.error(f"Failed to start session: {e}")
            raise
    
    async def end_session(self) -> Optional[dict[str, Any]]:
        if not self.is_active:
            return None
        
        self.is_active = False
        end_time = datetime.utcnow()
        
        duration = None
        if self.start_time:
            duration = int((end_time - self.start_time).total_seconds())
        
        try:
            await log_system_event(
                self.session_id,
                "Session ended",
                {"duration_seconds": duration}
            )
            
            session = await update_session(self.session_id, {
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "status": SessionStatus.COMPLETED.value
            })
            
            logger.info(f"Session ended: {self.session_id}")
            return session
            
        except Exception as e:
            logger.error(f"Failed to end session: {e}")
            raise
    
    async def resume_session(self) -> dict[str, Any]:
        try:
            session = await get_session(self.session_id)
            if not session:
                raise Exception(f"Session not found: {self.session_id}")
            
            self.is_active = True
            
            start_time_str = session.get("start_time", "")
            if start_time_str:
                if isinstance(start_time_str, str):
                    start_time_str = start_time_str.replace("Z", "+00:00")
                    try:
                        self.start_time = datetime.fromisoformat(start_time_str)
                    except ValueError:
                        self.start_time = datetime.utcnow()
                else:
                    self.start_time = datetime.utcnow()
            else:
                self.start_time = datetime.utcnow()
            
            await update_session(self.session_id, {
                "status": SessionStatus.ACTIVE.value,
                "end_time": None
            })
            
            logger.info(f"Session resumed: {self.session_id}")
            return session
            
        except Exception as e:
            logger.error(f"Failed to resume session: {e}")
            raise
    
    async def log_user_input(self, content: str) -> dict[str, Any]:
        return await log_user_message(self.session_id, content)
    
    async def log_ai_output(
        self, 
        content: str, 
        metadata: Optional[dict] = None
    ) -> dict[str, Any]:
        return await log_ai_response(self.session_id, content, metadata)
    
    async def log_tool_execution(
        self, 
        tool_name: str, 
        tool_input: dict
    ) -> dict[str, Any]:
        return await log_tool_call(self.session_id, tool_name, tool_input)
    
    async def log_tool_output(
        self, 
        tool_name: str, 
        result: Any
    ) -> dict[str, Any]:
        return await log_tool_result(self.session_id, tool_name, result)
    
    async def log_error_event(
        self, 
        error_message: str,
        metadata: Optional[dict] = None
    ) -> dict[str, Any]:
        return await log_error(self.session_id, error_message, metadata)
    
    async def get_session_info(self) -> Optional[dict[str, Any]]:
        return await get_session(self.session_id)
