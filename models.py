from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"


class EventType(str, Enum):
    USER_MESSAGE = "user_message"
    AI_RESPONSE = "ai_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SYSTEM = "system"
    ERROR = "error"


class WSMessageType(str, Enum):
    USER_INPUT = "user_input"
    AI_TOKEN = "ai_token"
    AI_COMPLETE = "ai_complete"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    SYSTEM = "system"
    PING = "ping"
    PONG = "pong"


class SessionBase(BaseModel):
    user_id: str


class SessionCreate(SessionBase):
    pass


class Session(SessionBase):
    id: UUID
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    summary: Optional[str] = None
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EventBase(BaseModel):
    session_id: UUID
    event_type: EventType
    content: str
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict)


class EventCreate(EventBase):
    pass


class Event(EventBase):
    id: UUID
    timestamp: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class WSMessage(BaseModel):
    type: WSMessageType
    content: str = ""
    metadata: Optional[dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WSUserInput(BaseModel):
    type: str = "user_input"
    content: str


class WSAIToken(BaseModel):
    type: str = "ai_token"
    token: str


class WSAIComplete(BaseModel):
    type: str = "ai_complete"
    content: str


class WSToolCall(BaseModel):
    type: str = "tool_call"
    tool_name: str
    tool_input: dict[str, Any]


class WSToolResult(BaseModel):
    type: str = "tool_result"
    tool_name: str
    result: Any


class WSError(BaseModel):
    type: str = "error"
    message: str


class SessionResponse(BaseModel):
    id: UUID
    user_id: str
    status: SessionStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    summary: Optional[str] = None


class CreateSessionRequest(BaseModel):
    user_id: str = Field(default="anonymous")


class CreateSessionResponse(BaseModel):
    session_id: UUID
    websocket_url: str
