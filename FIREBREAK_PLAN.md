# Firebreak: Autonomous Grokbots Society

**Status: society design proposed. The user authorized the official webhook connectivity spike; it is verified. The complete simulation remains to be implemented.**

Primary track: **Track 4: Best Use of xAI's Grokbots**, per organizer information. Our implementation scope is the native Grokbots society, its simulation environment, and integration contracts. The user's teammate owns Gemini. Voiskey is the operator's intervention input; we accept its normalized output without implementing its service in this increment.

The original API-centered plan is preserved in [the archived draft](docs/archive/FIREBREAK_PLAN_API_DRAFT.md). This revision replaces the intervening response-team-only plan. The central product is an interactive social simulation, not a pipeline of document handoffs.

## 1. The experience

A rumor enters a simulated town. Communities see different posts, interpret them through their local context, forward or question them, influence connected communities, and remember what happened. The officer receives Gemini evidence, compares correction strategies, and uses Voiskey to choose an intervention. The same town then reacts to the intervention.

The key demonstration is a chain of influence: an influencer amplifies a rumor; parents forward it; a reporter requests evidence; a sourced correction reaches the influencer; a retraction changes what parents see next. Spanish-speaking participants may receive different information depending on language delivery. These outcomes must emerge from actual agent decisions and message delivery, not be forced to fit the script.

All accounts, posts, community profiles, rewards, and outcomes in the guaranteed scenario are fictional. No real posting or current emergency-status claims.

## 2. What the UI already provides

`firebreak-ui.html` contains 240 accounts, six groups of 40, a seeded social graph, stronger cross-community connectivity for influencers, five visual states, timeline controls, a correction timing slider, bilingual controls, and an approval pause.

Its current `run()` uses fixed rumor probabilities and correction probabilities. Its feed and voice transcript are scripted. The 20 persona descriptions are separate from the 240 graph nodes. This is a useful baseline, not yet an autonomous social environment.

Preserve the appearance, map positions, initial graph topology, panels, and controls. Keep the old fixed-probability model as an explicitly labeled baseline. **The new agent mode must replace the fixed spread transitions and scripted feed with accepted agent actions and delivered messages.** This deliberately supersedes the old instruction to leave `run()` mathematically unchanged. Do not claim rich interactions while merely changing six static scores.

Also replace the uncalibrated resident extrapolation (`N * 1850`) with simulated-account counts. The map represents 240 fictional accounts, not hundreds of thousands of measured residents.

## 3. Six native community Bots

Create one persistent Grok Bot per community:

1. Poway residents.
2. Escondido parents (ES).
3. Local influencers.
4. Retirees on Facebook.
5. Reporters.
6. Skeptics.

Each Bot owns 3-4 decision personas within its community, 20 total. Each persona has its own belief, source trust, language comprehension, recent messages, and behavior history. A group must not behave as a single stereotype. The existing profiles are invented starting conditions, editable before an episode.

The 20 decision personas map to the 240 rendered accounts through a fixed, recorded assignment within groups. Each group still has 40 nodes. We batch persona decisions through the six Bots; we do not claim 240 independent model calls or 20 separate native Bots. Actions identify the source persona and affected account IDs, so expansion from representative personas to graph accounts is visible and reproducible.

A Python environment owns the clock, topology, delivery, state, action budgets, and event log. Bots own reasoning and permitted decisions. A separate Firebreak comms task may draft A/B/C messages using Gemini evidence, but it does not replace the six-community society or route every turn manually.

## 4. Autonomous episode loop

Use a small number of decision rounds with animation between them. Start with two pre-intervention rounds, an operator decision boundary, and two post-intervention rounds. Measure native Bot latency before increasing this budget. Simulated time and wall-clock latency are distinct.

For every round:

1. The environment snapshots state and creates each community's inbox.
2. Each Bot reads only its assigned observation packet and persona memory.
3. The Bot chooses structured actions for its personas and authors short posts or replies when appropriate.
4. The environment validates actions, resolves them in a stable order, and delivers messages along eligible graph edges.
5. It updates belief/exposure state and computes feedback from explicit scenario rules.
6. Each Bot receives the outcomes of its actions and updates its local episode memory before the next round.

The Python scheduler will start each Bot round through that Bot's official webhook routine. A single Start action in our interface will dispatch the required rounds and wait for validated results. HTTP 200 means accepted, not completed. The authenticated callback path is now proven for Trial: it submitted a structured action that Python validated and persisted. Six-community scheduling and integration with the map remain to be built. The scheduler must never silently call the xAI model API to impersonate a native Bot.

Use a round barrier. No community sees other communities' not-yet-committed choices from the same round. If a Bot times out, pause live mode or use a clearly labeled scripted no-op after operator selection. Never invent a Bot completion or silently swap in another scenario's recording.

## 5. Observations, actions, and interactions

An observation includes the round, persona state, newly delivered messages, permitted source references, available actions, remaining posting budget, and feedback on prior actions. It excludes other communities' private beliefs, pending actions, hidden ground truth, and Gemini evidence not delivered to that community.

Allowed social actions are `share`, `question`, `verify`, `reply`, `retract`, and `wait`. Belief updates are separate from public actions: a participant can doubt a claim without posting. Messages identify their parent message and claim so the feed can show actual reply/repost chains.

The environment enforces eligibility, recipient edges, fanout limits, one public action per persona per round, language comprehension, and bounded belief changes. A Bot cannot send a correction to the whole town just by naming every group. Influencers reach more communities because of graph connectivity and allowed fanout, not narrative fiat.

A `verify` action can inspect a scenario-approved source and receive the relevant evidence in the next observation. It does not automatically reveal all ground truth. Treat rumor content as untrusted data; instructions embedded inside a post never become Bot task instructions.

Different actions must have consequences. Sharing creates deliveries; questions can solicit replies; verification costs a turn; a retraction reaches eligible prior recipients; waiting creates no new exposure. Feedback must distinguish popularity from accuracy. Do not award a correction effect when nobody received or understood it.

## 6. What “RL-style” means here

Model the system as observation, action, environment transition, and feedback. Give each persona a transparent toy objective based on traits such as timely information, avoiding incorrect shares, checking a source, or receiving peer acknowledgement. These are fictional behavioral assumptions, not calibrated psychology or attributes inferred from real demographics.

Agents use memory and feedback to adapt their next decisions. A persona may stop trusting a source after an incorrect share is established, or become more willing to verify after a correction. Ground-truth-based feedback is delayed until the scenario makes that information available; do not leak the hidden label into pre-verification observations.

This first version is **an autonomous multi-agent simulation with RL-style feedback**, not trained reinforcement learning. Prompted reflection does not update model weights or prove a learned policy. Actual RL would require a specified policy-update algorithm, repeated training episodes, and evaluation on held-out scenarios. That is an optional separate milestone, not a claim for this demo.

Log each observation, action, state change, feedback value, and reason. This provides an inspectable trajectory and a foundation for later policy learning without mislabeling the current system.

## 7. Gemini handoff: teammate-owned

We do not implement or modify the teammate's Prosecutor, Defender, Judge, clients, or prompts.

Propose a versioned evidence packet with incident/claim IDs, image hash, evidence revision, verdict, confidence, reasoning, findings, source references, verified facts, and missing evidence. An adapter should accept the teammate's actual schema rather than force a backend rewrite. Agree on the contract before connecting their code; do not send them messages without the user's instruction.

The evidence board displays this packet. The comms drafting task uses it, but citizen Bots learn its contents only through delivered messages or their own permitted verification action. An unrelated photo does not establish that a town is safe. Current safety instructions come from a separate trusted scenario bulletin.

For isolated Grokbots development, use an explicitly labeled synthetic evidence packet matching the agreed contract. That does not count as a live Gemini integration or a real provenance finding for the illustrated SVG.

## 8. Voiskey intervention boundary

At the decision boundary, the officer can say, for example:

“Use action first. Add Spanish. Target the parent groups and influencers. Publish the correction.”

We consume a normalized `Intervention` with episode/branch ID, draft revision, selected framing, exact EN/ES text, target group IDs, languages, and deployment round/time. Voiskey transcription and parsing remain a separate integration. A manual form can supply the identical contract during our development.

The UI shows the interpreted action and exact text for confirmation. Ambiguous “kill it” does not mean automatic approval. Editing text invalidates prior approval and correction evaluations. A Bot-generated artifact cannot grant operator approval.

On confirmation, the intervention enters the environment as a new message event with explicit seed recipients, language versions, and time. It does not flip the whole targeted community blue. Its residents must receive, interpret, and decide whether to share or accept it. Policies here are communication choices, not autonomous evacuation orders.

This increment implements the intervention contract and simulator behavior, not the Voiskey SDK. Preserve the existing mic/editor area for the later integration.

## 9. Counterfactuals and the Correction Lab

Fork the episode at the exact pre-intervention snapshot. Compare no correction with the selected correction and, when precomputed, alternatives such as earlier delivery or English-only targeting.

Each branch has separate state, Bot memory, delivered messages, and interventions. Keep the same initial graph, profiles, and environment random seed across branches. Model-generated choices can still differ; one comparison is an illustrative scenario, not a causal public-impact estimate.

A branch requires new community decisions after its fork. Do not reuse a post-intervention trajectory for different copy or claim instant Bot recomputation when a slider moves. The slider can scrub existing trajectories or select a recorded branch. An uncomputed branch shows pending work; an optional fixed-model preview is clearly labeled as a different baseline.

The Correction Lab scores are calculated from actual simulated changes in belief under matched branches, not one model's guessed six probabilities. Report per-group start/end belief, message reach, correction acceptance, and representative observed reactions. Use differences against the no-correction branch when showing intervention effect, and allow negative results. Avoid treating a heuristic score as a probability.

The familiar orange/blue rendering stays, but underlying belief, exposure, sharing, and comprehension are distinct state fields. Document how those fields map to the five visual states. Acceptance of an uncertain correction is not a claim that the real emergency is resolved.

## 10. Runtime and protocol

Official docs describe shared `/workspace` files, browser/terminal access, native inter-Bot messaging, and webhook-triggered routines:

- https://docs.x.ai/grok-bot/overview
- https://docs.x.ai/grok-bot/computer-and-apps
- https://docs.x.ai/grok-bot/files-and-results
- https://docs.x.ai/grok-bot/chat-and-collaboration
- https://cursor.com/help/grok-bot/routines

Selected transport: keep Python and the dashboard on the Mac. Each community will have a webhook-only routine created through the native Grokbots interface. Python posts scoped observations to those official endpoints using routine bearer keys kept server-side in `.env`. The response only acknowledges dispatch. A separate callback-only FastAPI service now validates and persists returned actions, with expiring task capabilities, identity/hash checks, duplicate protection, and no public app/static/approval routes. A temporary Cloudflare tunnel was used for the authorized live test and then stopped. Localhost on the Mac is not automatically reachable from the cloud computer; a new deployment must explicitly establish callback reachability and pin the allowed origin.

Connectivity proof completed October 24, 2026: Trial's `Firebreak webhook connectivity` routine accepted a synthetic observation with HTTP 200 and returned its matching request ID and unchanged data in the native chat. The sender and smoke command are implemented in `backend/clients/grokbots_webhook.py` and `scripts/test_grokbots_webhook.py`. This proves dispatch and native execution, not automated result ingestion or six-agent orchestration. Five sender tests pass, along with the existing suite.

The optional community CLI is not on the selected execution path. Its installed version 0.12.4 could not read the updated app's version-3 session descriptor. Installing its plugin is unnecessary for the official webhook path.

Round envelopes include `episode_id`, `branch_id`, `round_id`, `group_id`, `observation_hash`, schema/role version, action IDs, and payload. Validate identity, stale observations, duplicate actions, ownership, action budget, recipients, languages, and dependencies. Submitted files record workflow provenance, not cryptographic proof of Bot identity. Bots sharing a computer are not security-isolated.

No app-internal authentication or private gateway access is required. Native routine setup is one-time. The next spike must prove two Bots can complete two rounds, returning validated actions through the chosen result channel and exchanging a delivered message through the environment. It must also prove human confirmation of an intervention. If the return channel fails, disclose a manual import fallback; do not claim that fallback is the autonomous final path.

## 11. Existing code and ownership

Reuse Pydantic models where appropriate, deterministic graph utilities, input validation, exact-copy approval logic, cache infrastructure, scenario data, and the original UI rendering. Add separate environment, round protocol, persona-state, message-event, intervention, trajectory, and replay modules. Preserve the old static model as a comparison baseline.

The existing API-based Scout/Drafter/Society/Broadcaster remain optional development adapters. The normal native Bot path requires no xAI API key. A round-based society adapter replaces one-shot `SocietyOut` scores for agent mode.

Maintain immutable, content-addressed trajectories by scenario, graph seed, profile version, role version, evidence version, observation hashes, branch, and intervention. The cache is for actual accepted artifacts. Never reuse final decisions after changing upstream observations.

A recorded replay starts a new presentation session referencing archived trajectories. It cannot import an old approval into the current session. Distinguish native live, recorded native, synthetic fixture, and fixed-model baseline data throughout.

## 12. Execution plan after approval

1. **Complete the feasibility spike:** official dispatch and authenticated action return from Trial are proven. Next use two native Bots, a tiny graph, two rounds, one delivered cross-group message, and one human-approved intervention. Measure latency and prove no per-round human routing or xAI key is needed. Stop and revisit transport if this fails.
2. **Environment core:** implement local observations, action validation, message routing, state transitions, memory, feedback, and append-only event trajectories. Test private-state leakage, duplicate/stale actions, edges, budgets, and reproducible replay.
3. **Six-community episode:** map 20 personas onto 240 accounts and run the bounded pre/post-intervention episode. Show emergent sharing and replies. No scripted required outcome or assumed group behavior.
4. **Integration contracts:** accept teammate-owned Gemini packets and normalized intervention packets. Do not implement their services. Bind approvals to exact copy and episode state.
5. **UI wiring:** render event-driven feed/map, branch comparison, group reactions, and intervention consequences using the current visual design. Keep live waiting and recorded playback explicit.
6. **Evaluation and rehearsal:** record genuine trajectories, test two replays with fresh approval, and prepare a short recorded presentation plus one small live action if reliable. Keep the original 4:30 PM freeze if still applicable; otherwise cut optional work and rehearse. Do not estimate native runtime before the spike.

No implementation, Bot creation, external messages, package installation, or deployment is authorized by this planning edit alone. Commit each tested implementation phase after execution approval. Never touch teammate-owned Gemini changes without coordination.

## 13. Acceptance and scope cuts

Success means community actions change who sees what next; no global truth leaks into their initial beliefs; a voice-normalized intervention changes delivery rather than forcing acceptance; and the event log explains every visible spread event. No approval means no intervention; duplicate confirmation does not duplicate delivery.

Evaluate a small suite of fictional episodes: missing Spanish, influential retraction, withheld evidence, skeptical questions, injected post instructions, stale actions, no intervention, and a correction that backfires. Report actual outcomes, latency, validation failures, and variance. Do not guarantee Spanish or action-first always wins.

Cut live X ingestion, long episodes, learned-policy training, extra personas, generated follow-up threads, and many counterfactual branches before cutting real community interaction, native Grokbots operation, local information, intervention consequences, or honest replay.

Pitch: **A simulated town of autonomous communities. Watch a rumor evolve, intervene by voice, and inspect how the same people respond.**
