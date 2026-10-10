"""Anonymous sessions and the agent chat endpoint (M41 + M33+34)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from packages.adapters.docstore import Table
from packages.agent.m33_agent import AgentRuntime, AgentSession, MockEngine, StrandsEngine
from packages.agent.tools import AgentTools
from packages.api.deps import AppState, StateDep
from packages.api.envelope import ApiResponse, ok
from packages.api.routers.health import engine_version
from packages.api.routers.solar import solar_inputs
from packages.core.city import load_city
from packages.core.errors import NotFoundError, ThrottledError, UpstreamTimeoutError
from packages.core.ids import new_session_id
from packages.services.policy_store import PolicyStore
from packages.services.repository import Repository

router = APIRouter(tags=["agent"])


class SessionOut(BaseModel):
    session_id: str


@router.post("/sessions", response_model=ApiResponse[SessionOut])
def create_session(request: Request, state: StateDep) -> Any:
    session = AgentSession(new_session_id())
    _save(state, session)
    return ok(SessionOut(session_id=session.session_id), request)


def _save(state: AppState, session: AgentSession) -> None:
    ttl = state.settings.session_ttl_hours * 3600
    state.adapters.docstore.put(
        Table.SESSION, f"session#{session.session_id}", "-", session.to_doc(), ttl_s=ttl
    )


def _runtime(state: AppState, city_slug: str) -> AgentRuntime:
    city = load_city(city_slug)
    discom = city.discom_for()
    c_lon = (city.bbox[0] + city.bbox[2]) / 2
    c_lat = (city.bbox[1] + city.bbox[3]) / 2
    s = state.settings
    tools = AgentTools(
        repo=Repository(state.adapters.docstore, state.adapters.blobstore),
        policies=PolicyStore(state.adapters.docstore),
        solar=solar_inputs(state).solar,
        params=state.params,
        blobs=state.adapters.blobstore,
        rules_dir=s.rules_dir,
        rules_version=s.rules_version,
        engine_version=engine_version(),
        city=city_slug,
    )
    mock = MockEngine(discom.state, discom.discom, c_lat, c_lon)
    engine: Any = mock
    if s.anthropic_api_key or s.bedrock_model_id:
        try:
            if s.runtime.value == "aws" and s.bedrock_model_id:
                from strands.models import BedrockModel

                engine = StrandsEngine(BedrockModel(model_id=s.bedrock_model_id))
            elif s.anthropic_api_key:
                from strands.models.anthropic import AnthropicModel

                engine = StrandsEngine(
                    AnthropicModel(
                        client_args={"api_key": s.anthropic_api_key.get_secret_value()},
                        model_id=s.anthropic_model,
                        max_tokens=800,
                    )
                )
        except Exception:  # SDK/provider unavailable: stay on the deterministic engine
            engine = mock
    return AgentRuntime(tools, engine, mock, max_turns=s.agent_max_turns)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    lang: str | None = Field(default=None, pattern="^(en|hi)$")
    ward_id: str | None = None
    city: str = "mini_city"


class ChatOut(BaseModel):
    reply: str
    citations: list[dict[str, str]]
    tool_calls: list[str]
    needs: list[str]
    pdf_url: str | None
    lang: str
    grounded: bool
    fallback_used: bool
    trace_id: str


@router.post("/agent/chat", response_model=ApiResponse[ChatOut])
def chat(body: ChatIn, request: Request, state: StateDep, x_session_id: str = Header(...)) -> Any:
    doc = state.adapters.docstore.get(Table.SESSION, f"session#{x_session_id}")
    if doc is None:
        raise NotFoundError("unknown or expired session; create one with POST /sessions")
    session = AgentSession.from_doc(doc)
    if body.ward_id:
        session.ward_id = body.ward_id
    try:
        reply = _runtime(state, body.city).respond(session, body.message, body.lang)
    except PermissionError as exc:
        raise ThrottledError("session turn limit reached; start a new session") from exc
    except TimeoutError as exc:
        raise UpstreamTimeoutError("agent timed out; retrying is safe") from exc
    _save(state, session)
    trace = request.state.request_id
    return ok(
        ChatOut(
            reply=reply.text,
            citations=reply.citations,
            tool_calls=reply.tool_calls,
            needs=reply.needs,
            pdf_url=reply.pdf_url,
            lang=reply.lang,
            grounded=reply.grounded,
            fallback_used=reply.fallback_used,
            trace_id=trace,
        ),
        request,
    )
