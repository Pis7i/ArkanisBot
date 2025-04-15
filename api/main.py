from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import json
from datetime import datetime, timedelta
import asyncio
from utils.logger import logger
from utils.security import security_manager
from utils.database import db_manager
from core.session import session_manager

# Initialize FastAPI app
app = FastAPI(
    title="ArkanisBot Admin API",
    description="Admin control panel API for ArkanisBot",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Pydantic models
class Token(BaseModel):
    access_token: str
    token_type: str

class UserSession(BaseModel):
    session_id: str
    phone: str
    created_at: datetime
    last_used: datetime
    active: bool

class ActionRequest(BaseModel):
    session_id: str
    action_type: str
    params: dict

# Authentication dependency
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = security_manager.verify_token(token)
    if payload is None:
        raise credentials_exception
    
    return payload

# Routes
@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login to get access token"""
    # In a real application, you would verify credentials against a database
    # For now, we'll use a simple check against environment variables
    if form_data.username != "admin" or not security_manager.verify_password(
        form_data.password,
        db_manager.get_cache("admin_password")
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = security_manager.create_access_token(
        data={"sub": form_data.username},
        expires_delta=timedelta(minutes=30)
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer"
    )

@app.get("/sessions", response_model=List[UserSession])
async def list_sessions(_: dict = Depends(get_current_user)):
    """List all sessions"""
    try:
        sessions = await session_manager.list_sessions()
        return [UserSession(**session) for session in sessions]
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list sessions"
        )

@app.post("/sessions/{session_id}/action")
async def execute_action(
    session_id: str,
    action: ActionRequest,
    _: dict = Depends(get_current_user)
):
    """Execute an action on a session"""
    try:
        # Get the client for this session
        client = await session_manager.load_session(session_id)
        if not client:
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )
        
        # Queue the action
        await client.queue_action(
            action.action_type,
            **action.params
        )
        
        return {"status": "success", "message": "Action queued"}
        
    except Exception as e:
        logger.error(f"Failed to execute action: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to execute action"
        )

@app.delete("/sessions/{session_id}")
async def end_session(
    session_id: str,
    _: dict = Depends(get_current_user)
):
    """End a session"""
    try:
        success = await session_manager.end_session(session_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Session not found or already ended"
            )
        
        return {"status": "success", "message": "Session ended"}
        
    except Exception as e:
        logger.error(f"Failed to end session: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to end session"
        )

# WebSocket endpoint for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Get current status
            sessions = await session_manager.list_sessions()
            
            # Send update
            await websocket.send_json({
                "type": "status_update",
                "data": {
                    "sessions": sessions,
                    "timestamp": datetime.utcnow().isoformat()
                }
            })
            
            # Wait before next update
            await asyncio.sleep(5)
            
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    ) 