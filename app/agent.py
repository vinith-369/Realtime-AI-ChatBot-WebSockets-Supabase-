import asyncio
import logging
from typing import Any, AsyncGenerator
from uuid import UUID

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool

from app.config import get_settings
from app.llm.tools import get_weather, calculate, search_knowledge, get_current_time

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a helpful AI assistant. Be friendly, helpful, and concise in your responses.

You have access to the following tools:
- get_weather: Get current weather for any location
- calculate: Perform mathematical calculations
- search_knowledge: Search knowledge base for information
- get_current_time: Get current date and time

When a user asks about weather, time, calculations, or knowledge topics, USE the appropriate tool to provide accurate information."""


def get_gemini_tools():
    weather_func = FunctionDeclaration(
        name="get_weather",
        description="Get the current weather for a location including temperature, conditions, and humidity",
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city or location to get weather for (e.g., 'Tokyo', 'New York', 'London')"
                }
            },
            "required": ["location"]
        }
    )
    
    calculate_func = FunctionDeclaration(
        name="calculate",
        description="Perform mathematical calculations including basic arithmetic and functions like sqrt, sin, cos, log",
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(16)', '15 * 8.5')"
                }
            },
            "required": ["expression"]
        }
    )
    
    knowledge_func = FunctionDeclaration(
        name="search_knowledge",
        description="Search the knowledge base for information on topics like Python, machine learning, WebSocket, climate, history",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter: general, science, history, technology",
                    "enum": ["general", "science", "history", "technology"]
                }
            },
            "required": ["query"]
        }
    )
    
    time_func = FunctionDeclaration(
        name="get_current_time",
        description="Get the current date and time",
        parameters={
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "The timezone (e.g., 'UTC', 'America/New_York')"
                }
            },
            "required": []
        }
    )
    
    return Tool(function_declarations=[weather_func, calculate_func, knowledge_func, time_func])


def execute_tool(tool_name: str, tool_args: dict) -> dict:
    if tool_name == "get_weather":
        return get_weather.invoke(tool_args)
    elif tool_name == "calculate":
        return calculate.invoke(tool_args)
    elif tool_name == "search_knowledge":
        return search_knowledge.invoke(tool_args)
    elif tool_name == "get_current_time":
        return get_current_time.invoke(tool_args)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


class ConversationAgent:
    def __init__(self, session_id: UUID):
        self.session_id = session_id
        self.settings = get_settings()
        self.conversation_history: list[dict] = []
        self.history_loaded = False
        
        try:
            genai.configure(api_key=self.settings.gemini_api_key)
            self.tools = get_gemini_tools()
            self.model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=SYSTEM_PROMPT,
                tools=[self.tools]
            )
            self.chat = self.model.start_chat(history=[])
            self.llm_available = True
            logger.info("Gemini model initialized with tools successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self.model = None
            self.chat = None
            self.llm_available = False
    
    async def load_history_from_db(self):
        if self.history_loaded or not self.llm_available:
            return
        
        try:
            from app.database import get_conversation_history
            
            events = await get_conversation_history(self.session_id)
            
            if events:
                gemini_history = []
                for event in events:
                    role = "user" if event["event_type"] == "user_message" else "model"
                    gemini_history.append({
                        "role": role,
                        "parts": [event["content"]]
                    })
                    local_role = "user" if event["event_type"] == "user_message" else "assistant"
                    self.conversation_history.append({
                        "role": local_role,
                        "content": event["content"]
                    })
                
                self.chat = self.model.start_chat(history=gemini_history)
                logger.info(f"Loaded {len(events)} messages from database for session {self.session_id}")
            
            self.history_loaded = True
            
        except Exception as e:
            logger.error(f"Failed to load history from database: {e}")
            self.history_loaded = True
    
    async def process_message(
        self, 
        user_message: str,
        stream_callback: callable = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        if not self.history_loaded:
            await self.load_history_from_db()
        
        if not self.llm_available or not self.chat:
            yield {
                "type": "error",
                "content": "Gemini not initialized. Check your GEMINI_API_KEY in .env"
            }
            return
        
        self.conversation_history.append({"role": "user", "content": user_message})
        
        try:
            response = await asyncio.to_thread(
                self.chat.send_message, 
                user_message
            )
            
            while response.candidates and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]
                
                if hasattr(part, 'function_call') and part.function_call.name:
                    func_call = part.function_call
                    tool_name = func_call.name
                    tool_args = dict(func_call.args)
                    
                    logger.info(f"Tool call: {tool_name} with args: {tool_args}")
                    
                    yield {
                        "type": "tool_call",
                        "tool_name": tool_name,
                        "tool_input": tool_args
                    }
                    
                    tool_result = execute_tool(tool_name, tool_args)
                    
                    logger.info(f"Tool result: {tool_result}")
                    
                    yield {
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "result": tool_result
                    }
                    
                    response = await asyncio.to_thread(
                        self.chat.send_message,
                        genai.protos.Content(
                            parts=[genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=tool_name,
                                    response={"result": tool_result}
                                )
                            )]
                        )
                    )
                else:
                    break
            
            if response and response.text:
                full_response = response.text
                
                words = full_response.split(' ')
                for i, word in enumerate(words):
                    token = word + (' ' if i < len(words) - 1 else '')
                    yield {
                        "type": "token", 
                        "content": token
                    }
                    await asyncio.sleep(0.02)
                
                self.conversation_history.append({"role": "assistant", "content": full_response})
                
                yield {
                    "type": "complete",
                    "content": full_response
                }
            else:
                yield {
                    "type": "error",
                    "content": "AI returned empty response. Your API quota may be exhausted."
                }
                
        except Exception as e:
            error_str = str(e)
            logger.error(f"Gemini error: {error_str}")
            
            if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower() or "exhausted" in error_str.lower():
                user_error = "API quota exceeded. Get a new key from https://aistudio.google.com/apikey"
            elif "api_key" in error_str.lower() or "invalid" in error_str.lower() or "API key" in error_str:
                user_error = "Invalid API key. Update GEMINI_API_KEY in your .env file"
            elif "blocked" in error_str.lower() or "safety" in error_str.lower():
                user_error = "Response blocked by safety filters. Try a different message."
            else:
                user_error = f"Error: {error_str[:120]}"
            
            yield {
                "type": "error",
                "content": user_error
            }
    
    def get_conversation_history(self) -> list[dict[str, str]]:
        return self.conversation_history.copy()
    
    def clear_history(self):
        self.conversation_history = []
        self.history_loaded = False
        if self.llm_available:
            try:
                self.chat = self.model.start_chat(history=[])
            except:
                pass
