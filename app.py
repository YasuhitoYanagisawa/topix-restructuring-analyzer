"""
FastAPI Server for TOPIX Analyzer
"""
import os
import json
import logging
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(override=True)

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="TOPIX Restructuring Analyzer")

# Create frontend directory if it doesn't exist
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
os.makedirs(frontend_dir, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

from topix_agent.agent import PipelineAgent

# Initialize custom pipeline agent
topix_agent = PipelineAgent()

import threading
from topix_agent.tools.stock_data import check_and_update_cache_if_needed

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up...")
    threading.Thread(target=check_and_update_cache_if_needed, daemon=True).start()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down...")

# Request Models
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the index.html"""
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Frontend not built yet.</h1>"

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """Chat endpoint using SSE for streaming responses"""
    
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            # Yield initial status
            yield f"data: {json.dumps({'type': 'status', 'content': 'Agent is thinking...'})}\n\n"
            
            # Use custom PipelineAgent directly
            async for chunk in topix_agent.generate_response(request.message, request.session_id):
                yield chunk
            
            yield f"data: {json.dumps({'type': 'status', 'content': 'Completed'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except Exception as e:
            logger.error(f"Error in chat stream: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
