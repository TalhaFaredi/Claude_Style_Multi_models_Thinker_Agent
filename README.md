# Claude-Style Multi-Model Thinker Agent

Multi-mode AI assistant with **Simple**, **Thinker**, and **Planner** execution paths. All modes share one model list, skills/tools, answer checker, and output pipeline.

> System design updated October 29, 2026.

## Overview

| Mode | What it does |
|------|----------------|
| **Simple** | One model answers; optional tool loop (max 10 calls). |
| **Thinker** | 2–5 agents work the same question; a **composer** merges their answers into one. |
| **Planner** | Writes a step-by-step plan; each step runs in Simple or Thinker and is checked before the next step. |

**Example:** *“Make a 2-page PDF report on solar power.”* Planner splits research → outline → writing → PDF. Research runs in Simple with web search; writing runs in Thinker; each step is checked; the user gets one PDF.

## Pipeline (all modes)

Every request passes the same stages; only the core run (stage 3) changes by mode.

1. **Input Gateway** — safety, history, memory, files  
2. **Mode Router** — user-selected mode or **Auto** (small model picks mode)  
3. **Run mode** — Simple, Thinker, or Planner  
4. **Checker** — validates draft against the question  
5. **Output Builder** — text, Markdown, PDF, PNG, web page, or code  

Shared services: Model Registry (OpenRouter / NVIDIA), Skills & Tools Hub, Memory & Files, Cost Meter, Fallback Manager, Logs & Feedback.

## Thinker mode (high level)

- **Agents:** 2–5 copies of the same model (different roles/temperatures) or 2–5 different models.  
- **Style:** **Independent** (parallel answers) or **Together** (debate rounds on a shared board; stop on agreement or after 3 rounds).  
- **Composer:** User-chosen model (default: strongest within budget); merges agreement and resolves conflicts.  
- **Fallback:** If the team fails, fall back to Simple with the best single model.

## Planner mode (high level)

- Plan requires user approval before steps run.  
- Each step: task, done-test, mode, tools, dependencies.  
- Max **2 retries** per step, max **2 re-plans**, plus budget, time limit, and user **Stop**.  
- Hard steps can use Thinker teams; easy steps stay in Simple.

## Safety & cost controls

- Budget guard before and during runs  
- Cost estimate before Thinker / Planner runs  
- Retry (2×) then model/provider fallback on API errors  
- Risky tools require user confirmation; code runs in a sandbox  

## Stack (this repo)

Backend dependencies (see `requirements.txt` when present):

- FastAPI + Uvicorn  
- httpx  
- python-pptx / python-docx (exports)  
- pytest / pytest-asyncio  

Models are routed via **OpenRouter** and **NVIDIA** through the Model Registry (price, context, tools, vision, thinking support).

## Status

Early-stage repository. Implementation is in progress.

## Author

[Muhammad Talha Fareedi](https://github.com/TalhaFaredi)

## License

TBD.
