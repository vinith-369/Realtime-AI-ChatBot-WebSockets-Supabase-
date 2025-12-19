import random
from datetime import datetime
from typing import Any

from langchain_core.tools import tool


@tool
def get_weather(location: str) -> dict[str, Any]:
    """Get the current weather for a location including temperature, conditions, and humidity."""
    conditions = ["Sunny", "Partly Cloudy", "Cloudy", "Rainy", "Stormy", "Snowy", "Foggy"]
    
    weather_data = {
        "location": location,
        "temperature_celsius": random.randint(-5, 35),
        "temperature_fahrenheit": 0,
        "condition": random.choice(conditions),
        "humidity_percent": random.randint(30, 90),
        "wind_speed_kmh": random.randint(0, 50),
        "timestamp": datetime.utcnow().isoformat()
    }
    weather_data["temperature_fahrenheit"] = round(
        weather_data["temperature_celsius"] * 9/5 + 32, 1
    )
    
    return weather_data


@tool
def calculate(expression: str) -> dict[str, Any]:
    """Perform mathematical calculations including basic arithmetic and functions like sqrt, sin, cos, log."""
    import math
    
    allowed_names = {
        "abs": abs, "round": round, "min": min, "max": max,
        "sum": sum, "pow": pow, "len": len,
        "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
        "tan": math.tan, "log": math.log, "log10": math.log10,
        "pi": math.pi, "e": math.e, "ceil": math.ceil, "floor": math.floor
    }
    
    try:
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return {
            "expression": expression,
            "result": result,
            "success": True
        }
    except Exception as e:
        return {
            "expression": expression,
            "error": str(e),
            "success": False
        }


@tool
def search_knowledge(query: str, category: str = "general") -> dict[str, Any]:
    """Search the knowledge base for information on topics like Python, machine learning, WebSocket, climate, history."""
    knowledge_base = {
        "python": {
            "title": "Python Programming Language",
            "content": "Python is a high-level, interpreted programming language known for its simplicity and readability. Created by Guido van Rossum and first released in 1991.",
            "category": "technology"
        },
        "machine learning": {
            "title": "Machine Learning",
            "content": "Machine Learning is a subset of AI that enables systems to learn and improve from experience. Key types include supervised, unsupervised, and reinforcement learning.",
            "category": "technology"
        },
        "websocket": {
            "title": "WebSocket Protocol",
            "content": "WebSocket is a communication protocol providing full-duplex channels over a single TCP connection. Ideal for real-time applications like chat and live updates.",
            "category": "technology"
        },
        "climate": {
            "title": "Climate Change",
            "content": "Climate change refers to long-term shifts in temperatures and weather patterns. Human activities, particularly burning fossil fuels, are the main driver since the 1800s.",
            "category": "science"
        },
        "renaissance": {
            "title": "The Renaissance",
            "content": "The Renaissance was a cultural movement from the 14th to 17th century, beginning in Italy. It marked the transition from medieval to modern times.",
            "category": "history"
        }
    }
    
    query_lower = query.lower()
    results = []
    
    for key, info in knowledge_base.items():
        if query_lower in key or key in query_lower:
            if category == "general" or info["category"] == category:
                results.append(info)
    
    if not results:
        results.append({
            "title": f"Search results for: {query}",
            "content": f"I found some information about '{query}'. This is a simulated knowledge base response demonstrating the tool calling capability.",
            "category": category
        })
    
    return {
        "query": query,
        "category": category,
        "results": results,
        "result_count": len(results)
    }


@tool
def get_current_time(timezone: str = "UTC") -> dict[str, Any]:
    """Get the current date and time for a specified timezone."""
    from datetime import datetime
    
    now = datetime.utcnow()
    
    return {
        "timezone": timezone,
        "datetime": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day_of_week": now.strftime("%A"),
        "note": f"Time shown in {timezone} (simulated)"
    }


AVAILABLE_TOOLS = [
    get_weather,
    calculate,
    search_knowledge,
    get_current_time
]


def get_tool_descriptions() -> str:
    descriptions = []
    for tool in AVAILABLE_TOOLS:
        descriptions.append(f"- {tool.name}: {tool.description}")
    return "\n".join(descriptions)
