from typing import Dict, Set
from fastapi import WebSocket
import json
import asyncio
from datetime import datetime
from utils.logger import logger

class WebSocketManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.last_status_update: Dict = {}
    
    async def connect(self, websocket: WebSocket):
        """Connect a new WebSocket client"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("New WebSocket client connected")
        
        # Send current status immediately
        if self.last_status_update:
            await self.send_personal_message(
                json.dumps(self.last_status_update),
                websocket
            )
    
    def disconnect(self, websocket: WebSocket):
        """Disconnect a WebSocket client"""
        self.active_connections.remove(websocket)
        logger.info("WebSocket client disconnected")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send a message to a specific client"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")
            await self.disconnect(websocket)
    
    async def broadcast(self, message: str):
        """Broadcast a message to all connected clients"""
        disconnected = set()
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Failed to send broadcast message: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
    
    async def broadcast_status(self, status: dict):
        """Broadcast status update to all clients"""
        self.last_status_update = {
            "type": "status_update",
            "data": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast(json.dumps(self.last_status_update))
    
    async def broadcast_event(self, event_type: str, data: dict):
        """Broadcast an event to all clients"""
        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast(json.dumps(message))

# Create a default WebSocket manager instance
websocket_manager = WebSocketManager() 