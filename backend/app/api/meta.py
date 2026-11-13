"""Health, configuration, models, settings, usage, skills, tools and the cost estimate."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import files, memory, prompts, skills, tools
from app.api.auth import require_admin
from app.api.common import defaults
from app.api.schemas import EstimateRequest
from app.core import auth, config, db, usage
from app.core.config import APP_VERSION, LIMITS
from app.llm import QUALITY_PRESETS, registry
from app.pipeline import estimate as estimator

router = APIRouter()


def reading_usage() -> dict:
    spent = usage.reading_spent()
    budget = float(memory.get_settings()["monthBudget"])
    percent = round(spent / budget * 100) if budget > 0 else (100 if spent else 0)
    return {"readingUsd": round(spent, 6), "readingBudgetPercent": percent, "readingAlarm": percent >= 80}


@router.get("/health")
async def health():
    try:
        db.one("SELECT 1")
    except Exception:   # noqa: BLE001 - the answer is the point, not the reason
        raise HTTPException(503, "database unavailable")
    return {"ok": True, "version": APP_VERSION}


def _providers_for_user() -> dict:
    """Provider health for the model picker. The operator's credit balance is for the operator only."""
    status = registry.provider_status
    user = auth.current_user()
    if config.AUTH_REQUIRED and not (user and user.is_admin):
        return {k: {"ok": v.get("ok"), "reason": "" if v.get("ok") else "Currently unavailable"} for k, v in status.items()}
    return status


@router.get("/api/config")
async def get_config():
    return {"monthCapUsd": round(usage.month_cap(), 4),
        "version": APP_VERSION, "defaults": defaults(), "qualityPresets": QUALITY_PRESETS,
        "limits": {"minAgents": LIMITS.min_agents, "maxAgents": LIMITS.max_agents, "minRounds": LIMITS.min_rounds, "maxRounds": LIMITS.max_rounds,
                   "maxToolCalls": LIMITS.max_tool_calls, "maxRetries": LIMITS.max_retries, "maxReplans": LIMITS.max_replans, "maxPlanSteps": LIMITS.max_plan_steps},
        "providers": _providers_for_user(), "readers": files.reader_availability(), "tools": tools.availability(),
        "capabilities": {"codeSandbox": any(t["name"] == "run_code" and t["available"] for t in tools.availability()),
                         "zipPassword": True, "embeddings": bool(db.get_setting("embeddings", True)), "webSearch": True},
        "settings": memory.get_settings(), "monthUsd": round(usage.month_spent(), 6), **reading_usage(),
    }


@router.get("/api/models")
async def list_models(q: str = "", all: bool = False, provider: str = ""):
    # The full catalog is the default. Keep `all` accepted for older clients.
    return [m.to_api() for m in registry.list(q[:100], include_all=True, provider=provider)]


@router.get("/api/prompts")
async def list_prompts():
    """Static shipped templates for review; never the rendered messages of a private run."""
    return {"version": APP_VERSION, "templates": prompts.catalog()}


@router.post("/api/providers/refresh")
async def refresh_providers():
    if config.AUTH_REQUIRED:
        require_admin()
    await registry.load(force=True)
    return await registry.probe_providers()


@router.get("/api/settings")
async def get_settings():
    return memory.get_settings()


@router.put("/api/settings")
async def put_settings(patch: dict):
    try:
        return memory.update_settings(patch)
    except ValueError as error:
        raise HTTPException(422, str(error))


@router.get("/api/usage")
async def get_usage():
    return {**usage.report(), "monthBudget": memory.get_settings()["monthBudget"], **reading_usage()}


@router.get("/api/skills")
async def list_skills():
    return skills.catalog()


@router.get("/api/tools")
async def list_tools():
    return tools.availability()


@router.post("/api/estimate")
async def post_estimate(body: EstimateRequest):
    req = {"mode": body.mode, "prompt": body.prompt, "simple": body.simple.model_dump(), "team": body.team.clamped(), "runIn": body.runIn, "planModel": body.planModel}
    chat_id = body.chatId if body.chatId and memory.get_chat(body.chatId) else None   # never read another account's chat
    out = await estimator.estimate(req, chat_id)
    if chat_id:
        out["context"] = await memory.meter(body.chatId, body.simple.model)
    return out
