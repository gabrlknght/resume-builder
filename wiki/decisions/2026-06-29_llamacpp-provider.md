---
title: ADR-006 — llama.cpp as a Local Provider with Reasoning Disable + Output Token Cap
type: decision
last_updated: 2026-06-29
sources: [customizer/pipeline.py, customizer/server.py, customizer/static/app.js]
---

# ADR-006: llama.cpp as a Local Provider with Reasoning Disable + Output Token Cap

- **Date:** 2026-06-29
- **Status:** Accepted
- **Context:** User moved to an AMD machine and needed local LLM inference via llama.cpp. Reasoning-capable models (e.g. Qwen3.x) burn thousands of tokens on hidden `<think>` chains before emitting the JSON `instructor` waits for. Small/local models on memory-bandwidth-bound hardware have no incentive to stop generating — a runaway call can take a minute+.

- **Decision:** Added `llamacpp` as a first-class provider alongside `ollama` with:
  - Default `base_url` of `http://localhost:8080/v1`
  - No API key required (local-only server)
  - `_disable_thinking_extra_body` injected on the `instructor` client → `{"chat_template_kwargs": {"enable_thinking": false}}` strips the model's reasoning/chain-of-thought before structured output.
  - `MAX_OUTPUT_TOKENS = 2048` enforced on every `instructor.from_callable` call (analyze, profile, experience, projects, cover letter) as a safety ceiling.
  - Frontend model-fetch: `GET /v1/models` from the configured base URL, auto-selects first available model.

- **Consequences:**
  - + Fast results on non-CUDA, memory-bandwidth-bound hardware (no CUDA dependency needed)
  - + Hidden reasoning chains cut out — smaller outputs, faster decode
  - + Output token cap prevents runaway generations from stalling the pipeline
  - - llama.cpp must be running separately (`llama.cpp` or `llama-server` on port 8080)
  - - User must load a compatible model into llama.cpp manually
