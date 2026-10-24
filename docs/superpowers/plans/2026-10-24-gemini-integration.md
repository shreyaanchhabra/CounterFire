# Gemini branch integration plan

**Goal:** Merge origin/gemini into main while retaining native Grokbots and presenting Gemini evidence and dictation in the existing desk.
**Architecture:** Preserve native society routes/contracts. Bring in Gemini agents/client and distinct schemas, then add a bounded evidence service and episode-specific analysis/voice routes. Use the current responsive desk with a source image, normalized evidence boxes, debate, confidence/reasoning, missing evidence asks, upload and dictation controls.
**Constraints:** No credential output, no live-to-fixture fallback, no new evidence after intervention approval, no voice-triggered automatic approval, no real publishing. Preserve original UI baseline and existing 80 tests.

- [x] Merge branch history, resolving overlapping core files in favor of the native controller and adapting Gemini schemas/config and scenario assets. Keep Gemini helper/eval/image tooling; preserve xAI scripts under existing names.
- [x] Add failing tests for normalized evidence, concurrent debate then judge, fixture provenance, native draft consumption, failed/late analysis preserving existing evidence, uploads, voice edits and approval invalidation.
- [x] Add bounded Gemini analysis workers and upload/voice/ask APIs. Bind evidence to incident and image hash; expose progress and sanitized errors. Model selection follows teammate client; no unsupported SDK assumptions.
- [x] Wire image overlays, findings, debate, uncertainty and dictation into the current UI. Keep imported JSON as an advanced fallback. Microphone requests occur only on the user's hold-to-record action.
- [x] Run full tests, verify fixture integration in browser, run live Gemini only if a key is configured, review, commit merged main and push origin/main.
