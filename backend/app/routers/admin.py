"""Admin dashboard endpoints: reasoning logs, sessions/traces, customers, escalations."""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.models import ResolveEscalationRequest
from app.prompts import active_version, available_versions, list_agents
from app.repositories import agent_logs_repo, refunds_repo, sessions_repo
from app.services import admin_service, escalation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/logs")
async def get_agent_logs(limit: int = 100) -> List[dict]:
    try:
        return await agent_logs_repo.list_recent(limit)
    except Exception as e:
        logger.error(f"Failed to get agent logs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/refund-decisions")
async def get_refund_decisions(limit: int = 100) -> List[dict]:
    try:
        return await refunds_repo.list_audit(limit)
    except Exception as e:
        logger.error(f"Failed to get refund decisions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/prompts")
async def get_prompt_versions() -> List[dict]:
    return [
        {"agent": agent, "active": active_version(agent), "versions": available_versions(agent)}
        for agent in list_agents()
    ]


@router.get("/stats")
async def get_admin_stats() -> dict:
    try:
        return await refunds_repo.decision_counts()
    except Exception as e:
        logger.error(f"Failed to get admin stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions")
async def list_admin_sessions(limit: int = 100) -> List[dict]:
    try:
        return await sessions_repo.list_recent(limit)
    except Exception as e:
        logger.error(f"Failed to list admin sessions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions/{session_id}")
async def get_admin_session(session_id: UUID) -> dict:
    try:
        return await admin_service.session_trace(session_id)
    except Exception as e:
        logger.error(f"Failed to get admin session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/customers/{customer_id}")
async def get_admin_customer(customer_id: int) -> dict:
    detail = await admin_service.customer_detail(customer_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return detail


@router.get("/escalations")
async def list_escalations(include_resolved: bool = False) -> List[dict]:
    try:
        return await escalation_service.list_pending(include_resolved)
    except Exception as e:
        logger.error(f"Failed to list escalations: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/escalations/{decision_id}/resolve")
async def resolve_escalation(decision_id: UUID, body: ResolveEscalationRequest) -> dict:
    result = await escalation_service.resolve(
        decision_id, body.action, body.reviewer[:255], body.reason.strip()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Escalated decision not found")
    return result
