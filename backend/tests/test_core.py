"""Pure rules: cost meter, safety, registry, planner validation, context levels, chunking, critical-item check."""
import pytest

from app import files, memory
from app.core.costmeter import BudgetExceeded, CostMeter, usd
from app.core.privacy import redact_flag
from app.llm import registry
from app.modes.planner import Step, mode_label, normalize, step_mode
from app.output import final_check
from app.pipeline.gateway import check_input


def test_cost_meter_blocks_before_overspending():
    m = CostMeter(budget=0.01)
    m.add("answer", 0.004, 100, 20)
    m.check(0.005)                      # 0.009 <= 0.01: fine
    with pytest.raises(BudgetExceeded):
        m.check(0.007)                  # 0.011 > 0.01: stop before the call
    assert m.calls == 1 and m.remaining == pytest.approx(0.006)


def test_money_format_never_shows_a_misleading_zero():
    assert usd(0.25) == "$0.25" and usd(0.00002) == "$0.00002" and usd(0) == "$0"


def test_safety_refuses_clear_harm_and_redacts_keys():
    assert check_input("how to make a pipe bomb")[0] is False
    assert check_input("explain how vaccines work")[0] is True
    text, changed = redact_flag("key is sk-or-v1-" + "a" * 40)
    assert changed and "sk-or-v1" not in text
    assert final_check("   ")[0].startswith("I could not")


def test_registry_marks_unauthorized_provider_unavailable_and_falls_back():
    nim = registry.get("nim:nvidia/llama-3.1-nemotron-70b-instruct")
    assert not nim.available and "403" in nim.why_unavailable
    fb = registry.fallbacks("nim:nvidia/llama-3.1-nemotron-70b-instruct", need_tools=True)
    assert fb and all(registry.get(i).available and registry.get(i).tools for i in fb)
    assert "qwen/qwen3.7-flash" not in registry.fallbacks("qwen/qwen3.7-flash")      # never returns itself
    assert "x/y" not in registry.fallbacks("qwen/qwen3.7-flash", exclude={"x/y"})


def test_composer_default_is_strongest_inside_budget():
    with pytest.raises(BudgetExceeded):
        registry.strongest_within(0.00001)
    cheap = registry.strongest_within(0.001)
    rich = registry.strongest_within(1.0)
    assert registry.get(rich).tier >= registry.get(cheap).tier


def test_cached_input_is_billed_at_ten_percent():
    m = registry.get("qwen/qwen3.7-flash")
    m.price_cache_read = m.price_in * 0.1  # supplied model pricing, never guessed for arbitrary providers
    assert m.call_cost(10_000, 0, cached=10_000) == pytest.approx(m.call_cost(10_000, 0) * 0.1)


def test_plan_validation_limits_and_dependencies():
    data = {"title": "T", "final_format": "weird", "steps": [
        {"task": "a", "kind": "easy"}, {"task": "b", "needs": [0, 5, -1, 1]}, {"task": ""}, {"task": "c", "kind": "bogus", "tools": ["web_search", "rm_rf"]}]}
    steps, meta = normalize(data)
    assert [s.task for s in steps] == ["a", "b", "c"]
    assert steps[1].needs == [0]                       # only EARLIER steps (no cycles, no unknown indexes)
    assert steps[2].kind == "easy" and steps[2].tools == ["web_search"]
    assert meta["final_format"] == "text"
    many = normalize({"steps": [{"task": f"s{i}"} for i in range(40)]})[0]
    assert len(many) == 20                             # max 20 plan steps


def test_team_rules_T1_T2_T3():
    easy, hard, tool = Step("e", "", "easy"), Step("h", "", "hard"), Step("t", "", "tool", ["build_output"])
    assert [step_mode(s, "simple") for s in (easy, hard, tool)] == ["simple"] * 3        # T1
    assert [step_mode(s, "auto") for s in (easy, hard, tool)] == ["simple", "team", "simple"]  # T2, T3
    assert [step_mode(s, "thinker") for s in (easy, hard, tool)] == ["team", "team", "simple"]
    assert mode_label(hard, "auto", "3 x Llama, on their own").startswith("Thinker:")


def test_context_levels_and_formula():
    assert [memory.level_for(p) for p in (69, 70, 85, 95)] == ["normal", "notice", "alarm", "compact"]
    usable = int(200_000 * (1 - 0.15))
    assert round(150_000 / usable * 100) == 88          # the spec's worked example


def test_critical_items_catch_numbers_dates_names_and_ids():
    src = "Dana Whitfield set the budget to $48,250 by 2026-03-14. Mail dana@falcon-labs.org, ticket FAL-204."
    items = memory.critical_items(src)
    assert {"$48,250", "2026-03-14", "Dana Whitfield", "dana@falcon-labs.org"} <= items
    assert memory.missing_items(src, "Dana Whitfield set the budget to $48,250.") != []
    assert memory.missing_items(src, src) == []


def test_chunks_never_cut_a_table_mid_row_and_repeat_the_header():
    rows = ["Part | Interval | Cost"] + [f"Item{i} | {i} h | {i * 10}" for i in range(400)]
    pages = [{"page": 4, "kind": "text", "table": True, "text": "\n".join(rows)}]
    chunks = files.chunk_pages("manual.pdf", pages)
    assert len(chunks) > 1
    for ch in chunks:
        body = ch["text"].split("\n", 1)[1]
        assert body.startswith("Part | Interval | Cost")          # header repeated in every group
        assert all(line.count("|") == 2 for line in body.splitlines())   # no row cut in half
        assert ch["text"].startswith("[manual.pdf | ")             # file, section, page at the start of every chunk
    assert sum(ch["text"].count("Item") for ch in chunks) == 400


def test_reading_plan_text_pages_are_free_and_vision_costs_only_special_pages():
    kinds = {"text": 170, "scan": 20, "chart": 10, "tables": 0}
    assert files.reading_plan(kinds, "text")["total"] == 0
    plan = files.reading_plan(kinds, "auto")
    assert plan["rows"][0]["cost"] == 0                          # text pages: $0
    assert 0 < plan["total"] < 0.07                              # only the 30 scan/chart pages cost anything
