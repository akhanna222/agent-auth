"""Agent registration and management routes."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from ..sandbox import SANDBOX_AGENTS, SANDBOX_CREATED_AT, get_sandbox_agent, wrap_response
from ..schemas.api.agents import AgentRegisterRequest, AgentRegisterResponse, AgentSummary
from ..services.identity import identity_service

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.post("/register", response_model=AgentRegisterResponse, status_code=201)
async def register_agent(request: Request, body: AgentRegisterRequest):
    tenant_id = request.state.tenant_id
    await identity_service.ensure_tenant(tenant_id)
    try:
        return await identity_service.register_agent(tenant_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_agents(request: Request):
    start_time = time.time()
    request_id = getattr(request.state, "request_id", None)
    tenant_id = request.state.tenant_id

    agents = await identity_service.list_agents(tenant_id)
    result = [
        AgentSummary(
            agent_id=a.agent_id,
            display_name=a.display_name,
            provider=a.provider,
            trust_tier=a.trust_tier,
            status=a.status,
            environment=a.environment,
            capabilities=a.capabilities,
            created_at=a.created_at,
        ).model_dump()
        for a in agents
    ]

    # Include sandbox agents if this is the mastercard-sandbox tenant
    if tenant_id == "mastercard-sandbox":
        existing_ids = {a["agent_id"] for a in result}
        for agent_id, agent_data in SANDBOX_AGENTS.items():
            if agent_id not in existing_ids:
                result.append({
                    **agent_data,
                    "created_at": SANDBOX_CREATED_AT,
                })

    # Return flat for UI, wrapped for MPGS (check Accept header or just return list)
    return result


@router.get("/{agent_id}")
async def get_agent(request: Request, agent_id: str):
    start_time = time.time()
    request_id = getattr(request.state, "request_id", None)

    # Check sandbox agents first
    sandbox_agent = get_sandbox_agent(agent_id)
    if sandbox_agent:
        data = {
            **sandbox_agent,
            "created_at": SANDBOX_CREATED_AT,
        }
        return wrap_response(data, request_id, start_time)

    agent = await identity_service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    data = AgentSummary(
        agent_id=agent.agent_id,
        display_name=agent.display_name,
        provider=agent.provider,
        trust_tier=agent.trust_tier,
        status=agent.status,
        environment=agent.environment,
        capabilities=agent.capabilities,
        created_at=agent.created_at,
    ).model_dump()
    return wrap_response(data, request_id, start_time)
