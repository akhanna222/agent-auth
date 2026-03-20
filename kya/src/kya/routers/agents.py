"""Agent registration and management routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

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


@router.get("", response_model=list[AgentSummary])
async def list_agents(request: Request):
    tenant_id = request.state.tenant_id
    agents = await identity_service.list_agents(tenant_id)
    return [
        AgentSummary(
            agent_id=a.agent_id,
            display_name=a.display_name,
            provider=a.provider,
            trust_tier=a.trust_tier,
            status=a.status,
            environment=a.environment,
            capabilities=a.capabilities,
            created_at=a.created_at,
        )
        for a in agents
    ]


@router.get("/{agent_id}", response_model=AgentSummary)
async def get_agent(request: Request, agent_id: str):
    agent = await identity_service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentSummary(
        agent_id=agent.agent_id,
        display_name=agent.display_name,
        provider=agent.provider,
        trust_tier=agent.trust_tier,
        status=agent.status,
        environment=agent.environment,
        capabilities=agent.capabilities,
        created_at=agent.created_at,
    )
