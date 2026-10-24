# Grok Agents Implementation Plan

**Goal:** Build Scout, Drafter, Society Sim, and Broadcaster from FIREBREAK_PLAN.md, without modifying the frontend or adding other providers.

**Architecture:** Pydantic contracts, an injectable OpenAI-compatible xAI client, and a shared disk cache. Each agent exposes `run(inputs, runner)` and returns an `AgentResult` containing a validated payload and `done` or `cached` status. A CLI exercises the complete Grok path with explicitly labeled synthetic fixtures or live requests.

**Spec:** FIREBREAK_PLAN.md, sections 5, 6.4, 6.8, 6.9, 6.10, and 7.

**Constraints:** Preserve the HTML and simulation. No real social posting. No invented model IDs or credentials. User explicitly deferred API setup and authorized building around missing credentials. No Gemini, Voiskey, FastAPI server, or frontend wiring in this scope.

## Tasks

- [ ] Contracts and cache: write failing unittest cases for bounded scores, unique groups and framings, input validation, replay without credentials, cache isolation, timeouts, and corrupt entries. Implement `backend/schemas.py` and `backend/cache.py`. Verify and commit.
- [ ] Client: test the real OpenAI SDK against an httpx mock transport for strict JSON, malformed output retry, narrowly scoped unsupported-format fallback, auth errors, refusals, and timeouts. Implement lazy configuration and `backend/clients/grok_client.py`. Verify and commit.
- [ ] Agents: test Scout cluster counts and timestamp velocity, evidence-dependent bilingual drafting, six-group simulation with zero-safe mapping, and approval-gated unchanged posts and reply matching. Implement four agent modules and the shared runner. Verify and commit.
- [ ] Demo and handoff: add 25 synthetic posts, 20 personas in the UI group order, labeled fixture outputs, and runnable offline/live/smoke CLI commands. Run the complete suite and offline CLI, document the exact key/model setup and remaining live verification, and commit.

## Review focus

- Input content is untrusted data, never instructions.
- Cache keys include all inputs, prompts, schema, model, and provider identity. Fixture cache cannot masquerade as a live result.
- Unknown or duplicate selected post IDs, duplicate group IDs, and missing reply IDs fail validation.
- Approval is required even during replay. Approved text is copied exactly, not regenerated.
- Synthetic evidence and audience scores are explicitly labeled. No asserted real emergency status comes from the sample scenario.

## Execution record

- Existing FIREBREAK_PLAN.md has user changes and will not be staged or altered.
- Work stays in the current shared checkout so the user can add credentials here.
- API/model confirmation and live verification are deferred by the user; the SDK boundary will be verified offline.
