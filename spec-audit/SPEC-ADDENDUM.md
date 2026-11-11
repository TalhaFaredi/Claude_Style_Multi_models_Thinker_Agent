# Multi-Mode AI Assistant: model, prompt and cost addendum (v2)

Updated November 11, 2026 (Asia/Seoul). This addendum extends the original 15-page `Multi-Mode_AI_Assistant_Complete_Spec (1).pdf`. It changes model visibility, displayed reasoning, prompt transparency and cost information. Fixed safety limits, approved spending caps and the original mode behavior remain in force.

## A1. Complete OpenRouter model catalog

- Show every model returned by the current OpenRouter model catalog, with search and provider filters. The initial list must not be limited to featured models. A refresh may update the catalog.
- Show model identity, provider, company, context limit, tool/image/thinking support, input/output prices, availability and any reason a model cannot be selected.
- Keep models with unknown prices or unavailable providers visible, but block selection for paid runs until a valid price and provider are available. Do not treat an unknown price as zero.

Acceptance: the count and IDs returned by `/api/models` match the loaded OpenRouter catalog plus configured NVIDIA entries; searching and provider filtering work; an unavailable model has an explicit reason and cannot bypass the budget guard.

## A2. Thinking in every mode

- The app may request bounded reasoning from models that support it in Simple, Thinker agents, the Thinker composer and Planner steps/teams. A model without the feature must still answer normally.
- Show each call's role/stage and model. Display reasoning notes only when the provider actually supplies them. When a provider supplies no reasoning text, say that notes were unavailable; never invent or reconstruct private reasoning.
- A reasoning request consumes tokens inside the same approved question budget. Reserve its maximum before dispatch and allow enough separate answer tokens to produce a visible response. Retain existing retry, fallback and Stop behavior.

Acceptance: a capable Thinker agent and composer request bounded reasoning and keep a nonempty answer allowance; an incapable model does not request the feature. Simple, Thinker and Planner display the provider's returned notes under the correct model/agent when available. Missing notes show an unavailable state. No run exceeds its approved cap because of reasoning.

## A3. Reviewable prompts for each agent

- Offer a read-only view of the shipped prompt templates: shared answer rules; Simple retry; Thinker agent, Solver, Critic, Fact-checker, Simplifier, Devil's advocate, independent agent, shared board, judge and composer; Planner plan writer, step and output formats; router and Checker; and supporting file/memory templates.
- Label whether each template is a system message, system fragment, user follow-up or response template. Explain that an effective call composes the shared rules, role template and runtime context. Show `$placeholders` as literal placeholders.
- The view must not return rendered user messages, uploaded documents, memories, tool outputs, API keys or another chat's content. A static template can be read even while the provider is offline.

Acceptance: `GET /api/prompts` returns the versioned static catalog with distinct IDs, titles, role labels and template text. It never inserts private runtime values. The UI lets the user read the shared rules and every team role's template.

## A4. Actual charge after each model call

- After a call finishes, show its model, role or stage, input tokens, output tokens, any reported reasoning tokens, charged USD and whether usage was estimated. Include retries, Checker, router, agents, composer and Planner calls in the run total.
- Failed or cancelled calls whose provider charge is unknown must be labelled as estimated. The answer's cost line must be the sum of recorded call charges rather than a projected price.
- Usage events contain metadata only, never prompt bodies or credentials.

Acceptance: each completed call emits a `call_usage` event and the final answer exposes total calls and USD. An estimated charge is visibly distinct from a provider-reported charge. Running two agents concurrently preserves each agent's role label without mixing their costs.

## A5. Tentative task-size prices for every model

- Show three approximate **single-call** price bands beside each priced model: small 1,000 to 5,000 total tokens, medium 5,000 to 50,000, high 50,000 to 500,000. Use current input/output prices and a documented 70% input, 30% output assumption; include per-request fees when published.
- Show a range of USD for the endpoints of each band. If the model's context cannot hold the whole band, identify the limit and do not present the full band as feasible. If a model cannot fit the minimum or its price is unknown, show unavailable instead of a numeric price.
- Label these bands **tentative**. They exclude cache discounts, image/tool usage, reasoning extras, retries, Checker and other agents. The question-specific estimate and approved cap still govern an actual run.

Acceptance: each priced model API row includes a small/medium/high estimate with token range, price range and feasibility. Test the formula against known model prices, an unknown-price model and a model with a short context window. The interface distinguishes tentative bands from actual post-call charges.

## A6. Verification and portability

- Offline tests cover catalog completeness, pricing math, role-labelled reasoning/usage events, prompt catalog privacy and Thinker reasoning capability handling.
- The updated README explains the new controls and their limits. A versioned PDF combines the original specification and this addendum; the original PDF is preserved unchanged.

Acceptance: both the versioned PDF and this Markdown addendum are available in the repository, and their requirements match the implemented API/UI contracts.
