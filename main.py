import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.websockets import WebSocketState

from app.config import get_settings
from app.models import (
    CreateSessionRequest, CreateSessionResponse, SessionResponse,
    WSMessageType
)
from app.database import create_session, get_session, get_conversation_history, Database, cleanup_empty_sessions
from app.llm.agent import ConversationAgent
from app.services.session import SessionManager
from app.services.summary import schedule_post_processing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Realtime AI Chat Backend...")
    settings = get_settings()
    
    if not settings.supabase_url or not settings.supabase_key:
        logger.warning("Supabase configuration missing - database features disabled")
    if not settings.gemini_api_key:
        logger.warning("Gemini API key missing - LLM features disabled")
    
    try:
        deleted = await cleanup_empty_sessions()
        if deleted > 0:
            logger.info(f"Startup cleanup: removed {deleted} empty sessions")
    except Exception as e:
        logger.error(f"Failed to cleanup sessions on startup: {e}")
    
    yield
    
    logger.info("Shutting down...")


app = FastAPI(
    title="Realtime AI Chat Backend",
    description="High-performance WebSocket-based conversational AI with LangGraph and Gemini",
    version="1.0.0",
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/sessions", response_model=CreateSessionResponse)
async def create_new_session(request: CreateSessionRequest):
    try:
        from app.models import SessionCreate
        session_data = SessionCreate(user_id=request.user_id)
        session = await create_session(session_data)
        
        session_id = session["id"]
        
        return CreateSessionResponse(
            session_id=UUID(session_id),
            websocket_url=f"/ws/session/{session_id}"
        )
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/{session_id}", response_model=SessionResponse)
async def get_session_details(session_id: UUID):
    session = await get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SessionResponse(
        id=UUID(session["id"]),
        user_id=session["user_id"],
        status=session["status"],
        start_time=session["start_time"],
        end_time=session.get("end_time"),
        duration_seconds=session.get("duration_seconds"),
        summary=session.get("summary")
    )


@app.get("/api/sessions")
async def list_sessions(limit: int = 20):
    client = Database.get_client()
    if not client:
        return {"sessions": []}
    
    try:
        result = client.table("sessions").select("*").order(
            "start_time", desc=True
        ).limit(limit).execute()
        
        return {"sessions": result.data or []}
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: UUID):
    try:
        messages = await get_conversation_history(session_id)
        return {"messages": messages}
    except Exception as e:
        logger.error(f"Failed to get messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/session/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: str):
    await websocket.accept()
    await asyncio.sleep(0.1)
    
    logger.info(f"WebSocket connected: {session_id}")
    
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        session_uuid = uuid4()
        session_id = str(session_uuid)
    
    existing_session = await get_session(session_uuid)
    session_manager = SessionManager(session_uuid)
    start_time = datetime.utcnow()
    
    try:
        if websocket.client_state != WebSocketState.CONNECTED:
            logger.warning(f"WebSocket connection closed before setup: {session_id}")
            return
        
        if existing_session:
            await session_manager.resume_session()
            logger.info(f"Resumed existing session: {session_id}")
        else:
            await session_manager.start_session()
            logger.info(f"Started new session: {session_id}")
        
        agent = ConversationAgent(session_uuid)
        
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await send_ws_message(websocket, {"type": "pong"})
                    continue
                
                user_input = message.get("content", "").strip()
                if not user_input:
                    continue
                
                await session_manager.log_user_input(user_input)
                
                full_response = ""
                
                async for chunk in agent.process_message(user_input):
                    chunk_type = chunk.get("type")
                    
                    if chunk_type == "token":
                        await send_ws_message(websocket, {
                            "type": "ai_token",
                            "token": chunk["content"]
                        })
                        full_response += chunk["content"]
                    
                    elif chunk_type == "tool_call":
                        await send_ws_message(websocket, {
                            "type": "tool_call",
                            "tool_name": chunk["tool_name"],
                            "tool_input": chunk["tool_input"]
                        })
                        await session_manager.log_tool_execution(
                            chunk["tool_name"],
                            chunk["tool_input"]
                        )
                    
                    elif chunk_type == "tool_result":
                        await send_ws_message(websocket, {
                            "type": "tool_result",
                            "tool_name": chunk["tool_name"],
                            "result": chunk["result"]
                        })
                        await session_manager.log_tool_output(
                            chunk["tool_name"],
                            chunk["result"]
                        )
                    
                    elif chunk_type == "complete":
                        await send_ws_message(websocket, {
                            "type": "ai_complete",
                            "content": chunk["content"]
                        })
                        if chunk["content"]:
                            await session_manager.log_ai_output(chunk["content"])
                    
                    elif chunk_type == "error":
                        await send_ws_message(websocket, {
                            "type": "error",
                            "message": chunk["content"]
                        })
                        await session_manager.log_error_event(chunk["content"])
            
            except WebSocketDisconnect:
                raise
            except json.JSONDecodeError:
                await send_ws_message(websocket, {
                    "type": "error",
                    "message": "Invalid message format"
                })
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                if websocket.client_state == WebSocketState.CONNECTED:
                    await send_ws_message(websocket, {
                        "type": "error",
                        "message": str(e)
                    })
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await schedule_post_processing(session_uuid, start_time)
        
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
        
        logger.info(f"Session cleanup complete: {session_id}")


async def send_ws_message(websocket: WebSocket, message: dict):
    try:
        if (websocket.client_state == WebSocketState.CONNECTED and 
            websocket.application_state == WebSocketState.CONNECTED):
            await websocket.send_json(message)
    except (WebSocketDisconnect, RuntimeError) as e:
        logger.debug(f"WebSocket closed during send: {e}")
    except Exception as e:
        logger.error(f"Failed to send WebSocket message: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
