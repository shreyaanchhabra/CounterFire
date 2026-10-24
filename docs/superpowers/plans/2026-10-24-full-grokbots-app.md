# Full Grokbots Application

Authorization: the user requested all Grokbot functionality for the app after approving and verifying official native webhook/callback transport. Execute the agreed society design in FIREBREAK_PLAN.md. Gemini and Voiskey services are outside our ownership; accept their normalized contracts.

## Tasks and file ownership

- Engine: `backend/society_models.py`, `backend/simulation.py`, `tests/test_simulation.py`. Build a deterministic six-group graph with 240 nodes, 20 representative personas, local observations, actual message deliveries, complete round barriers, feedback, and isolated branches. Tests first.
- UI: `frontend/index.html`, `frontend/styles.css`, `frontend/app.js`. Reuse the original visual design, render server trajectories, actual feed/reactions, correction selection and exact-copy approval, branches, and honest live/fixture/replay state. Do not edit original `firebreak-ui.html`.
- Main agent: official Bot job schemas, dispatch/orchestration, durable episodes, local FastAPI APIs/SSE, six Bot setup, comms task, recording/replay, callback-only public service, tests and documentation.

## Engine interface

`Simulation(seed=7, scenario=None, profiles=None, evidence=None)` loads existing data when arguments are omitted. `observation(group_id)->dict`; `apply_round(results: dict[int, dict])->dict` requires all six groups. Each result is `{group_id, decisions:[{persona_id, action, belief, message, parent_id}]}`. The observation advertises persona IDs and message IDs. Actions: share/question/verify/reply/retract/wait. `snapshot()->dict`, `fork(branch_id)->Simulation`, `intervene(intervention: dict)->None`. Intervention keys: text_en, text_es, target_groups, framing_key.

Snapshot contract: branch_id, round, sim_t, groups, network, frames, feed, feedback, personas. Network: edges (node pairs), groups (240 group IDs), persona_by_node. Frames: round, minute, states (240 ints matching original 0 unseen/1 sharing rumor/2 believes/3 sharing correction/4 accepts correction), events (`from`,`to`,`kind`), counts. Groups: id, name, belief (fraction), corrected (fraction), seen (count), reactions (strings). Feed: id, who, text, language, kind, round, parent_id, group_id. Feedback is inspectable fictional episode feedback, not trained RL.

## App API interface

`POST /api/episodes {mode:live|fixture|replay, recording_id?}`; `GET /api/episodes/{id}` returns view; `POST /api/episodes/{id}/advance` starts one round. `GET /api/health`; `GET /api/scenario`; `GET /api/recordings`; `GET /api/episodes/{id}/events` SSE. `POST .../evidence` accepts versioned teammate packet. `POST .../drafts` drafts corrections. `POST .../intervention` proposes text_en,text_es,target_groups,framing_key and returns view including pending_intervention {revision,content_hash,...}. `POST .../approve {revision,content_hash}` applies the exact proposal once. `POST .../branch {kind:none|correction, name?, intervention?}` creates independent counterfactual and returns view. `POST .../select-branch {branch_id}` selects one. `POST .../record` saves an immutable recording.

Episode view extends Simulation.snapshot with id, mode, status (ready/running/awaiting_approval/complete/error), version, error, pipeline (list of agent,status,summary), drafts ({framings:[Framing]} or null), evidence, pending_intervention, approval, branches (list of branch_id,round,belief,status), comparisons, pending_jobs. The adapter supplies sensible initial null/empty values. after 2 rounds await approval; after 4 rounds complete. A branch can run without intervention and records that choice explicitly. Fixture mode runs deterministic scripted decisions and clearly labels their origin. No real social publishing.

## State and safety checks

Never advance partially completed rounds. Bind actions to episode, branch, round, group and observation hash. Invalidate previous scores/approval after edits. Public callback receiver exposes only authenticated results, with no dashboard controls. Native Bots receive only local observations. Keep model memories separate between branches by including all authoritative memory in each observation and instructing Bots to ignore unrelated prior task facts.

## Verification

Run full unittest suite, Node JS syntax check, offline HTTP episode through approval and completion, branch independence/replay tests, then native group callback round and UI browser flow. Commit each independently tested phase. Preserve user/teammate changes.
