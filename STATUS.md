## A2A SWE-bench Status

### What’s Done
- **Green↔Purple A2A loop**
  - Green dispatches tasks to Purple via A2A client with timeouts.
  - Enforces reproduction gate: waits for `reproduction_script` artifact before accepting a patch.
  - Extracts patch artifacts and runs verification in provisioned Docker envs.
  - Cleans up containers in `finally`.
- **Purple agent alignment**
  - Wrapper emits two artifacts in order: reproduction (CODE, `metadata.type=reproduction_script`, `purpose=reproduction`) then patch (`metadata.type=patch_submission` or FILE_DIFF).
- **Dependency setup**
  - `requirements.txt` updated (pydantic 2.9.2; asyncpg commented out to avoid Python 3.13 build failures).
- **Docs/progress tracking**
  - PROGRESS.md maintained with current focus and risks.
- **Core components present (scaffolding)**
  - Trajectory capture & advanced scoring modules.
  - Ambiguity layer, reproduction gate, code reviewer personas.
  - Mutation/retro-holdout modules.
  - GitHub harvester & leaderboard scaffolding.

### What’s Still Missing / Gaps
- **Integration gaps**
  - Trajectory capture and advanced scoring not invoked in the main Green flow (no logger lifecycle; no post-verify scoring).
  - Dialogue manager/code review personas unused in the live path; no feedback artifacts.
  - Harvester/fresh scenarios not plumbed into ScenarioManager selection; always uses static/sample.
  - Mutation/retro-holdout not executed in live flow; no semantic equivalence check or mapping stored.
- **Environment robustness**
  - Docker hard requirement; no no-docker fallback.
  - No self-healing/synthesis integration beyond placeholders.
  - No resource limits or sandboxing controls surfaced.
- **Verification strength**
  - Relies on repo tests only; no fuzzing/mutation/adversarial checks or flaky-test detection.
  - Oracle tests optional; not consistently populated from scenarios; no fail-closed guard.
- **Model hookup**
  - Purple solver still mocked (SimpleSolver). No real Claude/GPT API path producing repro + patch.
  - No config/env wiring for provider/model/keys; no token/time budget enforcement; no retry/backoff on API errors.
- **Leaderboard/persistence**
  - DB/Redis optional; not wired in for metrics/leaderboard on completion.
- **Resilience**
  - No retry/backoff for Purple connectivity; limited observability/metrics exposed.

### Plan to Address Gaps

1) Wire telemetry and scoring
- Call TrajectoryCapture in Green: start logger per task; log environment setup, mutation steps, reproduction verification, patch verification, and artifact submissions.
- After verification, invoke AdvancedMetrics.calculate_comprehensive_score with trajectory + reproduction metrics; persist if DB is configured.
- Attach trajectory export and scores to the final artifact.
- Add a guard to always close/remove loggers when tasks complete/error.

2) Strengthen task flow with dialogue/review
- Integrate dialogue_manager for progressive info release when ambiguity is enabled.
- Add code_reviewer persona feedback loop post-patch verification; include feedback in metrics/artifacts.
- Emit a “review_feedback” artifact back to Purple if patch needs revision.

3) Solidify reproduction gate and Purple contract
- Keep reproduction mandatory in prod path; ensure errors clear and surfaced.
- Document expected artifact schema for Purple (repro then patch) and add lightweight schema validation on Green intake.
- Add retry/backoff for Purple task polling; make timeout configurable.

4) Environment robustness
- Add a `--no-docker`/mock mode: skip provisioning and use filesystem sandbox for fast smoke tests.
- Implement resource controls in EnvironmentOrchestrator (CPU/mem/timeouts on exec).
- Integrate basic synthesis/self-heal step: rerun `pip install -e . || true`, retry with common fixes, capture logs.

5) Verification hardness
- Add optional fuzzing/mutation-testing hook after patch verification for common Python patterns.
- Ensure oracle tests from scenarios are passed into VerificationEngine; fail closed if missing when required.
- Detect flaky tests (rerun on failure N times) and flag runs as “inconclusive” instead of silently failing.
- Add execution timeouts and per-command limits in verification to avoid hangs.

6) Mutation / anti-memorization
- Invoke RetroHoldoutGenerator in the live flow when `--enable-mutation` is set; apply semantic renames and track mappings.
- Run semantic equivalence check (tests before/after mutation); if divergence, revert mutations and continue.

7) Harvester integration for freshness
- Connect ScenarioManager to harvested scenarios table; prefer fresh (<24h) when enabled.
- Add flag to bypass static dataset and use harvested pool.

8) Model hookup for Purple
- Implement real solver that calls Claude/GPT APIs to produce reproduction script + patch.
- Add config/env for API keys and model selection; respect time/token budgets.
- Add retry/backoff and circuit-breaker on API errors; log token usage and latency.
- Validate outbound artifacts: ensure repro is CODE with purpose=reproduction; patch is FILE_DIFF with metadata.type=patch_submission.
- Provide a minimal prompt/template that requests: (a) failing reproduction first, (b) minimal unified diff next, (c) avoid path guessing; include repo root and constraints.

9) Leaderboard and persistence
- On task completion, persist Assessment/Result and push to LeaderboardService if DB configured.
- Expose minimal auth/pagination on leaderboard API for safe access.

10) Observability and ops
- Expose Prometheus metrics: tasks started/completed/failed, repro successes, verification durations, Purple timeouts.
- Structured logging with task_id/assessment_id.
- Basic health endpoint already present; add readiness check for Docker/DB/Redis where enabled.

