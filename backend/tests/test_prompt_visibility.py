"""Static prompt transparency and role-specific bounded reasoning; no provider calls."""
from __future__ import annotations

from app import prompts
from app.api.meta import list_prompts
from app.modes.planner.estimate import estimate_plan
from app.modes.planner.plan import Step
from app.pipeline import estimate as pricing
from app.pipeline.engine import manager


async def test_prompt_catalog_is_static_complete_and_role_labelled(fake_llm):
    private_marker = "SENTINEL_FROM_PRIVATE_USER_MESSAGE"
    prompts.render("thinker/agent", role=private_marker)
    response = await list_prompts()
    by_id = {entry["id"]: entry for entry in response["templates"]}
    assert len(by_id) == len(prompts.names())
    assert {"shared/system_rules", "simple/retry", "router/route", "checker/check", "thinker/agent",
            "thinker/composer", "planner/plan_writer", "planner/step"} <= by_id.keys()
    for role in ("solver", "critic", "fact_checker", "simplifier", "devils_advocate", "independent"):
        assert by_id[f"thinker/roles/{role}"]["role"] == "system fragment"
    assert by_id["shared/system_rules"]["role"] == "system"
    assert by_id["thinker/agent"]["content"].endswith("$role\nKeep your answer focused and under 350 words.")
    assert private_marker not in str(response)


async def test_thinker_requests_bounded_reasoning_with_separate_agent_labels(fake_llm, monkeypatch):
    from app import llm
    from tests.test_pipeline import collect, req

    labels = []
    async def capture(model, messages, *, stage, ctx=None, **kwargs):
        labels.append((stage, ctx.label if ctx else None))
        return await fake_llm(model, messages, stage=stage, ctx=ctx, **kwargs)
    monkeypatch.setattr(llm, "complete", capture)
    fake_llm.on("thinker:agent", "Supported answer.").on("thinker:compose", "Merged answer.").on("checker", {"pass": True})
    request = req("Compare A and B", mode="thinker", budgetUsd=1.0, team={
        "source": "same", "model": "qwen/qwen3.7-flash", "agents": 2, "mixed": [],
        "style": "independent", "rounds": 1, "composer": "qwen/qwen3.7-flash"})
    await collect(await manager.start(request))
    agents = [call for call in fake_llm.calls if call["stage"] == "thinker:agent"]
    composer = [call for call in fake_llm.calls if call["stage"] == "thinker:compose"]
    assert len(agents) == 2 and len(composer) == 1
    assert all(call["kw"]["thinking"] == "low" and call["kw"]["max_tokens"] >= 700 for call in agents)
    assert {label for stage, label in labels if stage == "thinker:agent"} == {"Solver", "Critic"}
    assert composer[0]["kw"]["thinking"] == "low"
    assert ("thinker:compose", "Composer") in labels


async def test_nonreasoning_thinker_model_stays_off(fake_llm):
    from tests.test_pipeline import collect, req

    fake_llm.on("thinker:agent", "Answer.").on("thinker:compose", "Merged answer.").on("checker", {"pass": True})
    request = req("Compare A and B", mode="thinker", budgetUsd=1.0, team={
        "source": "same", "model": "meta-llama/llama-3.1-8b-instruct", "agents": 2, "mixed": [],
        "style": "independent", "rounds": 1, "composer": "meta-llama/llama-3.1-8b-instruct"})
    await collect(await manager.start(request))
    assert all(call["kw"]["thinking"] == "off" for call in fake_llm.calls
               if call["stage"] in {"thinker:agent", "thinker:compose"})


async def test_thinker_and_planner_estimates_reserve_composer_reasoning():
    from app.llm import registry
    from tests.test_pipeline import req

    mid = "qwen/qwen3.7-flash"
    request = req("Compare A and B", mode="thinker", budgetUsd=1.0, team={
        "source": "same", "model": mid, "agents": 2, "mixed": [],
        "style": "independent", "rounds": 1, "composer": mid})
    result = await pricing.estimate(request, None)
    expected = pricing.call_cost(mid, 700 * 2 + 600 + max(20, len(request["prompt"]) // 4), 1200, "low")
    assert result["breakdown"]["composer"] == round(expected, 6)
    steps = [Step("Assess two choices", "A comparison is provided", "hard")]
    plan_request = {**request, "mode": "planner", "runIn": "thinker"}
    plan_price = estimate_plan(steps, plan_request)
    model = registry.get(mid)
    assert plan_price >= model.call_cost(2500 + 700 * 2, 1200 + 1024)
