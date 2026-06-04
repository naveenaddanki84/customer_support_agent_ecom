"""
WebSocket handler for real-time chat communication.
Uses complete LangGraph workflow for agent orchestration.
"""

import json
import logging
from typing import Dict
from uuid import UUID
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

from app.models import WebSocketMessage
from app.repositories import messages_repo, sessions_repo
from app.workflow import chat_workflow

logger = logging.getLogger(__name__)

# Active chat WebSocket connections, keyed by session id (string).
# Single-process registry — used to live-push admin notifications into a chat.
_active_connections: dict[str, "WebSocket"] = {}


async def push_to_session(session_id: str, payload: dict) -> bool:
    """Send a JSON payload to a session's live WebSocket if connected.

    Best-effort: returns True if a live socket received it, False otherwise.
    The message should already be persisted by the caller; this is only the
    real-time delivery.
    """
    ws = _active_connections.get(str(session_id))
    if ws is None:
        return False
    try:
        await ws.send_text(json.dumps(payload))
        return True
    except Exception as e:  # noqa: BLE001 - a dead socket just means no live delivery
        logger.warning(f"push_to_session failed for {session_id}: {e}")
        _active_connections.pop(str(session_id), None)
        return False




async def handle_websocket_connection(websocket: WebSocket, session_id: UUID):
    """Handle WebSocket connection lifecycle with complete workflow."""
    await websocket.accept()
    logger.info(f"WebSocket connected for session {session_id}")
    _active_connections[str(session_id)] = websocket

    # The signed-in customer's identity (their email) is stored on the session
    # row. This is the authoritative identity for refund ownership — never a
    # value derived from the session id, and never an email typed in the chat.
    session_row = await sessions_repo.get(session_id)
    authenticated_user_id = (session_row or {}).get("user_id") or f"user-{session_id}"

    try:
        # Send connection confirmation
        await websocket.send_text(json.dumps({
            "type": "system",
            "data": {"message": "Connected successfully", "session_id": str(session_id)}
        }))
        
        # Send message history
        history = await messages_repo.history(session_id)
        if history:
            await websocket.send_text(json.dumps({
                "type": "history",
                "data": {"messages": history}
            }))
        
        # Message handling loop
        while True:
            data = await websocket.receive_text()
            logger.info(f"WebSocket raw data received: {data}")
            ws_message = WebSocketMessage.parse_raw(data)
            
            if ws_message.type == "chat":
                user_content = ws_message.data.get("content", "")
                # Save user message
                user_metadata = ws_message.data.get("metadata", {})
                await messages_repo.insert(session_id, "user", user_content, "text", user_metadata)

                # Send user message back to client
                logger.info("About to send user message back to client")
                await websocket.send_text(json.dumps({
                    "type": "message",
                    "data": {
                        "session_id": str(session_id),
                        "sender": "user",
                        "content": user_content,
                        "message_type": "text",
                        "created_at": datetime.now().isoformat(),
                        "metadata": user_metadata
                    }
                }))
                logger.info("User message sent to client")
                
                # Process with complete workflow
                try:
                    workflow_result = await chat_workflow.process_message(
                        user_content, session_id, authenticated_user_id
                    )
                    
                    # Save agent response
                    await messages_repo.insert(
                        session_id, "assistant", workflow_result["content"], "text",
                        {
                            "agent": workflow_result["agent"],
                            "reasoning": workflow_result["reasoning"],
                            "decision": workflow_result.get("decision"),
                            "workflow_processed": True,
                        },
                    )
                    
                    logger.info("About to send workflow response to client")
                    # Send workflow response to client
                    await websocket.send_text(json.dumps({
                        "type": "message",
                        "data": {
                            "session_id": str(session_id),
                            "sender": "assistant",
                            "content": workflow_result["content"],
                            "message_type": "text",
                            "created_at": datetime.now().isoformat(),
                            "metadata": {
                                "agent": workflow_result["agent"],
                                "reasoning": workflow_result["reasoning"],
                                "decision": workflow_result.get("decision"),
                                "workflow_processed": True
                            }
                        }
                    }))
                    logger.info("Workflow response sent to client")
                    
                except Exception as workflow_error:
                    logger.error(f"Workflow processing error: {workflow_error}")
                    try:
                        logger.info("About to send fallback response to client")
                        await websocket.send_text(json.dumps({
                            "type": "message",
                            "data": {
                                "session_id": str(session_id),
                                "sender": "assistant",
                                "content": "I apologize, but I'm having trouble processing your request right now. Please try again.",
                                "message_type": "text",
                                "created_at": datetime.now().isoformat(),
                                "metadata": {"agent": "fallback"}
                            }
                        }))
                        logger.info("Fallback response sent to client")
                    except Exception as fallback_error:
                        logger.error(f"Error sending fallback response: {fallback_error}")
                
            elif ws_message.type == "heartbeat":
                # Respond to heartbeat
                await websocket.send_text(json.dumps({
                    "type": "heartbeat",
                    "data": {"timestamp": datetime.now().isoformat()}
                }))
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
    finally:
        _active_connections.pop(str(session_id), None)
        logger.info(f"WebSocket connection closed for session {session_id}")