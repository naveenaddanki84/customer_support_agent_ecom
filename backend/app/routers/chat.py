"""Public chat endpoints: sessions, customers, orders, agent info."""

import json
import logging
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.models import SessionCreate, SessionResponse
from app.repositories import customers_repo, messages_repo, orders_repo, sessions_repo
from app.services import agent_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


def _to_session_response(row: Dict[str, Any]) -> SessionResponse:
    metadata = row.get("metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    return SessionResponse(
        id=row["id"], user_id=row["user_id"], status=row["status"],
        created_at=row["created_at"], metadata=metadata or {},
    )


@router.post("/sessions", response_model=SessionResponse)
async def create_session(session_data: SessionCreate) -> SessionResponse:
    try:
        row = await sessions_repo.create(session_data.user_id, json.dumps(session_data.metadata))
        return _to_session_response(row)
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: UUID) -> SessionResponse:
    row = await sessions_repo.get(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_session_response(row)


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: UUID, limit: int = 50) -> List[dict]:
    try:
        return await messages_repo.list_by_session(session_id, limit)
    except Exception as e:
        logger.error(f"Failed to get messages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/sessions/{session_id}")
async def close_session(session_id: UUID) -> dict:
    row = await sessions_repo.close(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session closed successfully", "session_id": str(session_id)}


@router.get("/agent")
async def get_agent_info() -> dict:
    return agent_service.agent_info()


@router.get("/customers")
async def list_customers() -> List[dict]:
    try:
        return await customers_repo.list_all()
    except Exception as e:
        logger.error(f"Failed to list customers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users/{user_id}/sessions")
async def list_user_sessions(user_id: str) -> List[dict]:
    try:
        rows = await sessions_repo.list_by_user(user_id)
        for row in rows:
            title = (row.get("title") or "New chat").strip()
            row["title"] = (title[:48] + "…") if len(title) > 48 else title
        return rows
    except Exception as e:
        logger.error(f"Failed to list user sessions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users/{email}/orders")
async def list_user_orders(email: str) -> List[dict]:
    try:
        return await orders_repo.list_by_email(email)
    except Exception as e:
        logger.error(f"Failed to list user orders: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
