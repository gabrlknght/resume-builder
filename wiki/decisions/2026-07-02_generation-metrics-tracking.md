---
title: ADR-008 — Generation Metrics Tracking (Tokens/Time)
type: decision
last_updated: 2026-07-02
sources: [customizer/pipeline.py, customizer/history_manager.py, customizer/server.py, customizer/server_additions.py, customizer/static/app.js]
---

# ADR-008: Generation Metrics Tracking (Tokens/Time)

- **Date:** 2026-07-02
- **Status:** Accepted
- **Context:** Users running local providers (llama.cpp/Ollama) have no visibility into how expensive a tailoring or cover-letter run was — no token counts, no elapsed time, no throughput. This matters most for local inference, where a slow model or an overloaded GPU/CPU is a real, user-visible cost.

- **Decision:** Added a `MetricsTracker` (`pipeline.py`) that wraps every `instructor`-mediated LLM call (`analyze_jd`, `tailor_profile`, `tailor_experience`, `tailor_projects`, `generate_cover_letter`) via an async context manager. It sums `completion_tokens` (read from the `_raw_response.usage` that `instructor` attaches to the parsed Pydantic model) and tracks wall-clock elapsed time from pipeline start. The resulting `{elapsed_seconds, total_tokens}` is:
  - Attached to the `"final"` SSE event's `data.timing` for both `run_pipeline` and `run_cover_letter_pipeline`.
  - Captured client-side into `lastTailoringMeta.timing` and forwarded through `/api/generate`'s `_meta` payload.
  - Persisted into each history entry's `_meta.json` (`save_resume_history` / `save_cover_letter_history`) — omitted entirely when `None` rather than written as `null`, so pre-existing history entries degrade gracefully.
  - Rendered as a "METRICS" column in both history tables, as a metrics line in both preview panes (AI tailoring diff view and cover letter preview) via a shared `renderTimingHtml()` helper, and as a dashed secondary-axis ("Avg tok/s", right-side `y1` scale) line on the Stats tab's Chart.js chart — `_aggregate_history()` now computes `avg_tokens_per_sec` and `avg_elapsed_seconds` per bucket from whatever entries in that bucket have timing data.

- **Related fix:** Debugging this surfaced a `llamacpp`-provider request timeout (`openai.APITimeoutError`) in Stage 3. Most llama.cpp servers run a single inference slot, so the 3 concurrent `asyncio.gather` calls (profile/experience/projects) actually queue server-side even though the client fires them in parallel — the last-queued call could exceed the previous 120s client timeout while still waiting. Raised the `llamacpp` client timeout to 600s (`get_instructor_client`) to give queued calls room to finish; concurrency itself was left as-is since it also serves cloud providers where parallel calls genuinely help.

- **Consequences:**
  - + Users get per-generation throughput (tok/s) and duration visibility across history tables, preview panes, and a trend chart
  - + Metrics degrade gracefully for history predating this feature (shown as `—`, chart shows a gap via `spanGaps`)
  - + Timeout fix reduces spurious Stage 3 failures for local providers under 2+ concurrent requests
  - - Token counts rely on the provider actually returning a `usage` block on non-streaming completions — some OpenAI-compatible local servers may not populate it, in which case `total_tokens` reads 0 but `elapsed_seconds` is still accurate
  - - `MetricsTracker.track()` tries four fallback paths to locate `usage` on the instructor response (`resp.usage`, `resp._raw_response.usage`, `resp.model_extra["usage"]`, `resp.extra["response"].usage`) since the exact attachment point isn't guaranteed across instructor versions/providers
  - - Local providers (llamacpp/ollama) still fire Stage 3 concurrently despite typically single-slot servers — the 600s timeout papers over the queuing rather than avoiding it; a future change could serialize Stage 3 for local providers specifically
