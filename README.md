# Realtime AI Chat Backend

A high-performance, asynchronous Python backend for real-time conversational AI using WebSockets, LangChain/LangGraph, Gemini API, and Supabase.

## Features

- Real-time WebSocket Communication
- LangChain/LangGraph Integration
- Function/Tool Calling (weather, calculator, knowledge search, time)
- Supabase Persistence
- Post-Session Summaries
- Modern Chat UI

---

## Prerequisites

- Python 3.10+
- Supabase account (free tier works)
- Google Gemini API key

---

## Setup Instructions

### 1. Clone and Setup

```bash
git clone <repository-url>
cd ChatBot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

**Required packages:**

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.115.6 | Web framework |
| uvicorn[standard] | 0.34.0 | ASGI server |
| websockets | 14.1 | WebSocket protocol |
| python-dotenv | 1.0.1 | Environment variables |
| pydantic-settings | 2.7.0 | Configuration |
| supabase | 2.11.0 | Database client |
| langchain | 0.3.13 | LLM orchestration |
| langchain-google-genai | 2.0.8 | Gemini integration |
| langgraph | 0.2.60 | Agent state management |
| httpx | 0.28.1 | Async HTTP client |

### 3. Configure Environment

Create `.env` file:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
GEMINI_API_KEY=your-gemini-api-key
```

### 4. Setup Database

Run the SQL schema from `supabase/schema.sql` in your Supabase SQL Editor.

---

## Running the Server

### Development

```bash
uvicorn app.main:app --reload --port 8000
```

### Production

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser.

---

## Testing the WebSocket

### Using wscat

```bash
npm install -g wscat
wscat -c ws://localhost:8000/ws/session/test-session-123

# Send message:
{"type": "user_input", "content": "What's the weather in Tokyo?"}
```

### WebSocket Message Types

**Client → Server:**
```json
{"type": "user_input", "content": "Your message"}
{"type": "ping"}
```

**Server → Client:**
```json
{"type": "ai_token", "token": "streaming..."}
{"type": "ai_complete", "content": "Full response"}
{"type": "tool_call", "tool_name": "get_weather", "tool_input": {...}}
{"type": "tool_result", "tool_name": "get_weather", "result": {...}}
{"type": "error", "message": "Error description"}
{"type": "pong"}
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Chat UI |
| GET | `/health` | Health check |
| POST | `/api/sessions` | Create session |
| GET | `/api/sessions` | List sessions |
| GET | `/api/sessions/{id}` | Get session |
| GET | `/api/sessions/{id}/messages` | Get messages |
| WebSocket | `/ws/session/{id}` | Real-time chat |

---

## Project Structure

```
ChatBot/
├── app/
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── llm/
│   │   ├── agent.py
│   │   └── tools.py
│   └── services/
│       ├── session.py
│       └── summary.py
├── static/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── supabase/
│   └── schema.sql
├── requirements.txt
└── .env
```

---

## Design Choices

### WebSocket for Real-time Communication
Full-duplex, low-latency streaming of AI responses token-by-token for responsive UX.

### LangGraph for Agent Orchestration
Structured state management and tool binding with seamless LangChain integration.

### Supabase for Persistence
PostgreSQL with REST API - no ORM needed. Async client fits FastAPI's architecture.

### Token Streaming
Immediate feedback as AI generates responses, reducing perceived latency.

### Post-Session Processing
Background tasks for summary/name generation avoid blocking real-time chat.

### Simulated Tools
Demonstrate function-calling capability without external API dependencies. Easily replaceable with real APIs.

---

## License

MIT
