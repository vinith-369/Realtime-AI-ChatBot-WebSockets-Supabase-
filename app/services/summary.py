import asyncio
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.database import (
    get_conversation_history, finalize_session, get_session,
    delete_session, get_session_message_count, get_first_user_message, update_session
)

logger = logging.getLogger(__name__)


SUMMARY_SYSTEM_PROMPT = """You are an AI assistant that summarizes conversations. 
Given a conversation history, create a concise summary that captures:

1. Main topics discussed
2. Key questions asked by the user
3. Tools/functions that were used (if any)
4. Important outcomes or conclusions

Keep the summary brief (2-4 sentences) but informative.
Format the summary as a clear, readable paragraph.
"""


CHAT_NAME_SYSTEM_PROMPT = """You are an AI assistant that creates short, descriptive titles for chat conversations.
Given a conversation summary, create a brief title (3-5 words maximum) that captures the main topic.

Rules:
- Keep it very short: 3-5 words maximum
- Be descriptive but concise
- Don't use quotes or special characters
- Capitalize appropriately like a title
- Focus on the main topic discussed

Examples:
- "User asked about cooking pasta and received recipe instructions" → "Pasta Recipe Help"
- "Discussed Python debugging techniques and fixed a loop error" → "Python Debugging Session"
- "User inquired about weather forecast for the weekend" → "Weekend Weather Forecast"
- "Explained machine learning concepts and neural networks" → "Machine Learning Basics"
"""


async def generate_chat_name(summary: str) -> str:
    settings = get_settings()
    
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0.3
        )
        
        messages = [
            SystemMessage(content=CHAT_NAME_SYSTEM_PROMPT),
            HumanMessage(content=f"Create a short title for this conversation summary:\n\n{summary}")
        ]
        
        response = await llm.ainvoke(messages)
        name = response.content.strip()
        
        name = name.strip('"\'')
        
        if len(name) > 50:
            name = name[:47] + "..."
        
        logger.info(f"Generated chat name: {name}")
        return name
        
    except Exception as e:
        logger.error(f"Failed to generate chat name: {e}")
        fallback = summary[:30] + "..." if len(summary) > 30 else summary
        return fallback


async def generate_session_summary(session_id: UUID) -> Optional[str]:
    settings = get_settings()
    
    try:
        events = await get_conversation_history(session_id)
        
        if not events:
            return "No conversation took place in this session."
        
        conversation_text = []
        for event in events:
            role = "User" if event["event_type"] == "user_message" else "Assistant"
            conversation_text.append(f"{role}: {event['content']}")
        
        conversation_str = "\n".join(conversation_text)
        
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0.3
        )
        
        messages = [
            SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
            HumanMessage(content=f"Please summarize this conversation:\n\n{conversation_str}")
        ]
        
        response = await llm.ainvoke(messages)
        summary = response.content
        
        logger.info(f"Generated summary for session {session_id}")
        return summary
        
    except Exception as e:
        logger.error(f"Failed to generate summary for session {session_id}: {e}")
        return f"Summary generation failed: {str(e)}"


async def process_session_end(session_id: UUID, start_time: datetime) -> dict:
    logger.info(f"Starting post-session processing for {session_id}")
    
    end_time = datetime.utcnow()
    duration_seconds = int((end_time - start_time).total_seconds())
    
    try:
        message_count = await get_session_message_count(session_id)
        
        if message_count == 0:
            logger.info(f"Session {session_id} has no messages, deleting...")
            deleted = await delete_session(session_id)
            
            return {
                "session_id": str(session_id),
                "status": "deleted" if deleted else "delete_failed",
                "reason": "empty_session"
            }
        
        summary = await generate_session_summary(session_id)
        
        chat_name = None
        if summary:
            chat_name = await generate_chat_name(summary)
            await update_session(session_id, {"name": chat_name})
        
        session = await finalize_session(
            session_id=session_id,
            summary=summary or "No summary available",
            end_time=end_time,
            duration_seconds=duration_seconds
        )
        
        logger.info(f"Session {session_id} finalized. Name: {chat_name}, Duration: {duration_seconds}s")
        
        return {
            "session_id": str(session_id),
            "name": chat_name,
            "summary": summary,
            "duration_seconds": duration_seconds,
            "end_time": end_time.isoformat(),
            "status": "completed"
        }
        
    except Exception as e:
        logger.error(f"Post-session processing failed for {session_id}: {e}")
        return {
            "session_id": str(session_id),
            "error": str(e),
            "status": "error"
        }


async def schedule_post_processing(session_id: UUID, start_time: datetime):
    asyncio.create_task(
        process_session_end(session_id, start_time),
        name=f"post_process_{session_id}"
    )
    logger.info(f"Scheduled post-processing for session {session_id}")
