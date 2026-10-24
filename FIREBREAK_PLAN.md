# Firebreak: Build Plan for Claude Code

> Hand this whole file to Claude Code along with `firebreak-ui.html`.
> Hackathon: **Five Nights with AI** (ACM AI x TESC, UC San Diego), Sat Oct 24 2026, 8 AM to 6 PM.
> Target tracks: **Track 2 Best Use of Voiskey**, **Track 3 Best Use of SpaceX AI (Grok)**, **Track 4 Best Use of Google Gemini**.
> Hard deadline: feature freeze at **4:30 PM**. Everything after that is rehearsal.

---

## 0. Instructions to Claude Code (read first)

You are building **Firebreak**, a misinformation response desk for county emergency comms teams. The frontend design is **already done**: it is the file `firebreak-ui.html`. Your job is to wire real AI agents into that exact UI.

**Rules:**

1. **Do not redesign the UI.** Keep every color token, font, layout, panel, and the spread simulation exactly as they are in `firebreak-ui.html`. You are replacing hardcoded demo data with live data, nothing more. If you need a new element (an upload button, a persona quote), match the existing styles and tokens.
2. **Keep the spread simulation math unchanged** (`run()`, `hr()`, graph build, `pFire`, the 0.2 conversion factor, the age > 12 burnout). It is tuned. Only the per-group correction probabilities (`FR[x].p`) and the Spanish multiplier become data driven.
3. **No build step.** Plain HTML/CSS/JS frontend served by FastAPI. No React, no bundler. We do not have time.
4. **Every agent result gets cached to disk.** The demo must never depend on live API latency. See Section 7.
5. **Nothing posts to real social media.** The Broadcaster posts into the in-app feed only.
6. **Before writing API clients, ask me for anything you can't find.** I have the SDKs, docs, and keys on this laptop. Look first (check `~/Downloads`, the project folder, installed pip packages), then ask. Specifically confirm with me:
   - Gemini API key and the exact model names available (`client.models.list()`)
   - xAI / Grok API key, the exact Grok model names, and whatever "Grok bots" SDK or docs the SpaceX AI track provided
   - Voiskey SDK / API docs location, API key, and what Voiskey returns (raw transcript only? cleaned text? translation? command parsing?)
7. Commit after each phase with a clear message.
8. Write all user-facing copy in plain language, short sentences, no em dashes.

---

## 1. The product in one paragraph

During a disaster, a fake post (example: a recycled 2019 Arizona fire photo captioned "the fire jumped I-15, Poway get out now") spreads faster than officials can respond. People jam evacuation roads, flood 911, or ignore real orders. Firebreak catches the rumor as it spikes (Grok Scout), has two Gemini agents argue over the actual image (Prosecutor vs Defender), has a Gemini Judge rule on it, drafts three corrections (Grok), tests them on a simulated town of Grok personas (Society Sim), lets the comms officer approve and edit by voice (Voiskey), then posts and answers replies (Grok Broadcaster). The Spread Map shows the correction (blue) racing the rumor (orange) through six communities.

---

## 2. Sponsor track mapping (put this on a slide too)

| Agent | Sponsor | What it does | Why it's a strong "best use" |
|---|---|---|---|
| Scout | **Grok** | Clusters incoming posts into one incident, extracts the core claim, flags velocity | Real-time social understanding is Grok's home turf. If the track's Grok tools give live X search, use it in live mode |
| Prosecutor | **Gemini** | Multimodal image forensics: signs, landmarks, shadows, weather, plus bounding boxes; Google Search grounding for earlier copies | Uses Gemini vision + spatial understanding (box_2d) + grounding, not just text |
| Defender | **Gemini** | Steelmans the claim with supporting evidence | Adversarial setup reduces one-sided verdicts |
| Judge | **Gemini** | Verdict, confidence, missing evidence, as strict JSON | Structured output drives the UI directly |
| Drafter | **Grok** | Writes 3 correction framings (fact check, action first, neighbor voice) | |
| Society Sim | **Grok bots** | 6 persona groups react to each framing; scores drive the map's spread math | Multi-persona simulation is the flashiest Grok use and it visibly changes the map |
| Broadcaster | **Grok** | Posts approved correction to in-app feed and answers reply questions in thread | |
| Editor | **Voiskey** | Comms officer speaks messy orders, gets clean posts + commands that control the app | Voice is a core control, not a bolt-on: approve, kill, add Spanish, all by voice |

---

## 3. Tech stack and configuration

- **Python 3.11+**
- **Backend:** FastAPI + uvicorn, Server-Sent Events (SSE) for live agent updates (`sse-starlette`)
- **Gemini:** `google-genai` SDK (`from google import genai`)
- **Grok:** xAI API. It is OpenAI-compatible: use the `openai` SDK with `base_url="https://api.x.ai/v1"`, or the `xai-sdk` if that's what's installed. Use whichever the track docs recommend.
- **Voiskey:** whatever SDK/API I give you. Wrap it in an adapter (Section 6.8).
- **Validation:** Pydantic v2 models for every agent output
- **Frontend:** the existing HTML split into `index.html`, `styles.css`, `sim.js`, `app.js`. Mic via `MediaRecorder` (works on `localhost` since it's a secure context).

**`requirements.txt`**
```
fastapi
uvicorn[standard]
sse-starlette
python-multipart
python-dotenv
pydantic>=2
google-genai
openai
httpx
cairosvg
datasets
```
(Add the Voiskey SDK package once confirmed.)

**`.env.example`**
```
GEMINI_API_KEY=
GEMINI_MODEL=            # confirm with client.models.list(); use a fast flash-class model for agents
XAI_API_KEY=
GROK_MODEL=              # confirm via GET https://api.x.ai/v1/models
GROK_FAST_MODEL=         # optional cheaper model for the 18 persona calls
VOISKEY_API_KEY=
VOISKEY_BASE_URL=        # if REST
DEMO_MODE=hybrid         # replay | live | hybrid
```
Add `.env` and `cache/` raw responses with secrets to `.gitignore`. Never commit keys.

---

## 4. Project structure

```
firebreak/
├── backend/
│   ├── main.py              # FastAPI app, routes, static serving, SSE
│   ├── config.py            # env loading, DEMO_MODE
│   ├── schemas.py           # Pydantic models (Section 5)
│   ├── cache.py             # get_or_run(key, fn) disk cache
│   ├── pipeline.py          # orchestrator, emits SSE events in order
│   ├── clients/
│   │   ├── gemini_client.py
│   │   ├── grok_client.py
│   │   └── voiskey_client.py
│   └── agents/
│       ├── scout.py
│       ├── prosecutor.py
│       ├── defender.py
│       ├── judge.py
│       ├── drafter.py
│       ├── society.py
│       ├── broadcaster.py
│       └── editor.py        # Voiskey + intent parsing
├── data/
│   ├── scenario_sd1024.json # scripted posts, claim, timing
│   ├── personas.json        # 6 groups, 20 personas
│   ├── viral.png            # rasterized from the UI's SVG (Section 6.2)
│   └── eval_claims.json     # 30 labeled claims (Section 9)
├── frontend/
│   ├── index.html
│   ├── styles.css
│   ├── sim.js               # spread sim, unchanged math
│   └── app.js               # UI wiring
├── scripts/
│   ├── rasterize_svg.py
│   ├── smoke_test.py        # one call per API, prints OK/FAIL
│   ├── warm_cache.py        # runs full pipeline once in live mode, saves everything
│   └── run_eval.py
├── cache/
├── .env.example
├── requirements.txt
└── README.md
```

Run: `uvicorn backend.main:app --reload --port 8000`, open `http://localhost:8000`.

---

## 5. Data contracts (Pydantic schemas)

The UI reads exactly these shapes. Keep field names.

```python
class Incident(BaseModel):
    incident_id: str            # "SD-1024"
    claim: str                  # one sentence, the core claim
    post_count: int
    velocity_per_min: float
    languages: list[str]        # ["en", "es"]
    summary: str

class Finding(BaseModel):
    id: int                     # 1, 2, 3 -> numbered tags on the image
    label: str                  # short, plain language, <= 90 chars
    box_2d: list[int] | None    # [ymin, xmin, ymax, xmax] normalized 0-1000, None if not a region
    category: Literal["location","shadow_light","weather","provenance","account","other"]

class ProsecutorOut(BaseModel):
    findings: list[Finding]     # max 3 shown
    bullets: list[str]          # max 3, <= 50 chars each, for the debate column

class DefenderOut(BaseModel):
    bullets: list[str]          # max 3, <= 50 chars each

class MissingEvidence(BaseModel):
    item: str                   # "Original file from uploader"
    ask_target: str             # "@sd_firewatch_live" or "CAL FIRE PIO"

class JudgeOut(BaseModel):
    verdict: Literal["False","Misleading","Unverified","True"]
    confidence: int             # 0-100
    reasoning: str              # 1-2 sentences
    missing: list[MissingEvidence]  # max 2

class Framing(BaseModel):
    key: Literal["A","B","C"]
    name: str                   # "Fact check" | "Action first" | "Neighbor voice"
    text_en: str                # <= 280 chars
    text_es: str                # <= 280 chars

class GroupScore(BaseModel):
    group_id: int               # 0-5, matches GROUPS order in the UI
    belief_drop: float          # 0-1
    reaction: str               # one short in-character quote
class SocietyOut(BaseModel):
    framing_key: str
    scores: list[GroupScore]            # 6 entries
    es_group_en_only_drop: float        # Escondido parents score if they only get English

class VoiceIntent(BaseModel):
    action: Literal["approve","kill","edit","none"]
    languages: list[str]
    facts: list[str]            # facts the officer stated ("photo is from 2019")
    framing_hint: Literal["A","B","C"] | None

class EditorOut(BaseModel):
    raw: str                    # exactly what Voiskey heard
    clean: str                  # Voiskey cleaned text
    filler_spans: list[list[int]]   # [start,end] char ranges in raw to strike through
    command_spans: list[list[int]]  # [start,end] ranges to highlight purple
    intent: VoiceIntent
    post_en: str
    post_es: str | None
```

**SSE event shape** (`GET /api/stream`):
```json
{"agent": "judge", "status": "running|done|cached|error", "sim_t": 14, "summary": "False · 91% confident", "payload": { ... }}
```

---

## 6. Step by step implementation

### Phase 0: Setup (15 min)
1. Create the folder structure above. `python -m venv .venv && pip install -r requirements.txt`.
2. Ask me for the keys and SDK locations listed in Section 0 rule 6. Fill `.env`.
3. Write `scripts/smoke_test.py`: one tiny call each to Gemini (text), Gemini (image), Grok (text + JSON), Voiskey (a short audio file I'll record, or a sample from their docs). Print model names that work. **Do not continue until all four pass or I say skip.**

### Phase 1: Clients (30 min)

**6.1 `gemini_client.py`**
```python
from google import genai
from google.genai import types
client = genai.Client(api_key=GEMINI_API_KEY)

def gemini_json(prompt: str, schema, image_bytes: bytes | None = None, mime="image/png"):
    parts = []
    if image_bytes:
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
    parts.append(prompt)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
        ),
    )
    return schema.model_validate_json(resp.text)

def gemini_grounded_text(prompt: str) -> str:
    # Google Search grounding. Some API versions don't allow grounding + response_schema
    # in one call, so: grounded call returns text, then gemini_json() structures it.
    resp = client.models.generate_content(
        model=GEMINI_MODEL, contents=prompt,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
    )
    return resp.text
```

**6.2 `grok_client.py`**
```python
from openai import OpenAI
grok = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")

def grok_json(system: str, user: str, schema, model=GROK_MODEL):
    resp = grok.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()}},
        temperature=0.7,
    )
    return schema.model_validate_json(resp.choices[0].message.content)
```
If structured output isn't supported on the model I have, fall back to "Return only JSON matching this schema: ..." and validate with Pydantic, retry once on failure. If the SpaceX AI track gave a specific "Grok bots" SDK, use it instead and keep this function signature.

**6.3 `voiskey_client.py`** (adapter, fill in after reading their docs)
```python
class VoiskeyClient:
    def transcribe_and_clean(self, audio: bytes, mime: str) -> tuple[str, str]:
        """Return (raw_transcript, clean_text). Use Voiskey for as much as it supports."""
```
**Important for Track 2:** read the Voiskey docs fully. If Voiskey supports cleanup, formatting, commands, translation, or tone, use Voiskey for those instead of Gemini. Judges score depth of Voiskey usage. Only use Gemini for steps Voiskey can't do.

**Raster the image:** `scripts/rasterize_svg.py` extracts the `<svg>` inside `.photo` from `firebreak-ui.html` (remove the dashed boxes group and number tags first, so Gemini sees a clean image) and writes `data/viral.png` at 1080px wide with `cairosvg`. The sign text "101 NORTH / Scottsdale Rd" is what Gemini should catch.

### Phase 2: Agents and pipeline (60 min)

Write each agent as a function `run(inputs) -> SchemaOut`, wrapped by `cache.get_or_run(key, fn)`.

**6.4 Scout (Grok)**
- Input: the scripted posts from `data/scenario_sd1024.json` (5 visible posts + ~20 extra short variants you generate once for realism, including 4 in Spanish).
- System prompt:
  > You are Scout, a monitoring agent for a county emergency communications team during an active wildfire. Given a batch of social posts, group the ones making the same factual claim into one incident. Extract the single core claim in plain language. Note languages present. Be literal. Do not judge truth.
- Velocity is computed in Python from post timestamps, not by the model.

**6.5 Prosecutor (Gemini, vision + grounding)**
- Input: `viral.png`, the claim, post time "7:20 PM PDT, Oct 24", location "I-15 at Rancho Bernardo, San Diego County", poster account age "9 days".
- Step 1, vision with boxes:
  > You are a forensic image analyst. The post claims: "{claim}". It was posted at {time} and says the location is {location}. Find evidence this image is NOT what the post claims. Check: readable signs and text, landmarks, road and terrain features, shadow direction vs claimed time, weather and smoke direction, signs of editing or AI generation. For each visual finding, return box_2d as [ymin, xmin, ymax, xmax] normalized to 0-1000. Max 3 findings. Labels must be short and plain, like "Sign reads Loop 101, Scottsdale Rd. That's Arizona, not I-15."
- Step 2, grounded search (`gemini_grounded_text`): "Has an image matching this description appeared online before {date}? Description: {Gemini's own description of the image}". If it finds nothing, the provenance finding says "No earlier copy found" (don't invent one).
- Merge into `ProsecutorOut`.

**6.6 Defender (Gemini)**
  > You are the Defender. Argue as strongly and honestly as you can that the post could be real. Use the image and context. Give up to 3 short points. Don't make things up; if support is weak, say so.
- Context to pass: "A real fire is active about 6 miles east. Winds are from the northeast at 25 mph."

**6.7 Judge (Gemini, strict JSON)**
  > You are the Judge. Read the Prosecutor's and Defender's arguments. Output a verdict, a confidence from 0-100, one or two sentences of reasoning, and up to 2 pieces of missing evidence that would most change your confidence, each with who to ask. Be calibrated: only go above 90 if the location or provenance evidence is decisive.

**6.8 Drafter (Grok)**
  > Write 3 corrections for a county emergency account. Each under 280 characters, plain language, 6th grade reading level, include the safety action. A = Fact check (lead with FALSE and why). B = Action first (lead with what residents should do, then debunk). C = Neighbor voice (from the perspective of a local resident on the scene). Also give a natural Spanish version of each (not literal translation, written for Spanish-speaking parents in North County San Diego).

**6.9 Society Sim (Grok bots)**
- `data/personas.json`: 6 groups matching the UI's `GROUPS` order exactly:
  0 Poway residents, 1 Escondido parents (ES), 2 Local influencers, 3 Retirees on Facebook, 4 Reporters, 5 Skeptics. 3-4 personas per group, 20 total, each with name, age, platform, trust in government (low/med/high), language.
- One Grok call per framing (3 calls) returning all 6 group scores, OR one call per group per framing (18 calls, run with `asyncio.gather`) if you want per-persona reactions. Use `GROK_FAST_MODEL` if available.
- System prompt per persona group:
  > You are simulating how this group of real people would react on social media. You already saw and partly believed this post: "{claim}". Now you see this correction: "{text}". Stay in character. Return belief_drop from 0 (still fully believe the rumor) to 1 (fully convinced it was false), and one short in-character reaction.
- For group 1, score twice: with `text_es` and with only `text_en`. Store the English-only result as `es_group_en_only_drop`.

**Mapping scores into the existing sim (exact):**
```js
FR[key].p = scores.map(s => clamp(0.3 * s.belief_drop, 0.03, 0.32));
ES_OFF_MULT = clamp(es_group_en_only_drop / scores[1].belief_drop, 0.1, 1.0); // replaces the hardcoded 0.25
```
The heat cells in the Correction Lab already display `round(p / 0.3 * 100)`, so they will show the persona scores directly. The "Sim pick" badge goes on the framing with the highest average.

**6.10 Broadcaster (Grok)**
- On approval, adds the approved posts to the feed. Then answers 3 scripted replies (put them in the scenario file): "so is poway safe or not??", "why should we trust the county, you were late last time", "¿y Ramona? ¿también?". Answers are friendly, short, point to ReadySanDiego, never invent new orders. Keep the "@CountyComms_demo" handle.

**6.11 Editor (Voiskey, then intent)**
1. `POST /api/voice` with audio from the browser.
2. Voiskey returns raw + clean (or raw only; then do cleanup with Gemini).
3. Compute `filler_spans` (tokens in raw like um/uh/like/okay so that aren't in clean) and `command_spans` (phrases that map to intent: "kill it", "approve", "do Spanish too", "stay off the roads").
4. Intent parsing: use Voiskey if it supports commands, else Gemini with `VoiceIntent` schema:
   > Extract the comms officer's instruction. action: approve/kill/edit/none. "kill it" about a rumor means publish the correction (approve). Languages requested. Facts they stated.
5. Rewrite the selected framing's EN/ES text to include stated facts, staying under 280 chars.

**6.12 `pipeline.py` orchestrator**
- Timeline is synced to the map clock so agents "finish" while the rumor spreads, and everything is ready at the T+24 auto-pause:

| Sim minute | Event |
|---|---|
| T+2 | Scout done |
| T+6 | Prosecutor running, Defender running (parallel) |
| T+12 | Prosecutor done, Defender done |
| T+15 | Judge done |
| T+18 | Drafter done |
| T+22 | Society Sim done |
| T+23 | Editor ready (cached voice note) |
| T+24 | Map pauses, Broadcaster "Waiting for approval" |

- The frontend sends its current sim minute; backend emits each event once the clock passes it. In `replay` mode results come from cache; in `live` mode agents run immediately and events are held until their minute.

**Endpoints**
```
GET  /                     -> frontend/index.html
GET  /api/health           -> which APIs are reachable, DEMO_MODE
GET  /api/scenario         -> posts, claim, image url, groups, scripted replies
POST /api/pipeline/start   -> starts a run, returns run_id
GET  /api/stream?run_id=   -> SSE agent events
POST /api/analyze          -> multipart image + claim text; runs Prosecutor/Defender/Judge live (judge-brings-own-image moment)
POST /api/voice            -> multipart audio -> EditorOut
POST /api/broadcast        -> {framing_key, post_en, post_es} -> replies
POST /api/draft_ask        -> {item, ask_target} -> short message text for the "Draft ask" buttons
```

### Phase 3: Frontend wiring (60 min)

Split `firebreak-ui.html` into the 4 frontend files. Then, without changing the look:

1. **Pipeline strip:** each `.agent` gets `data-agent="scout"` etc. On SSE event: `dot` class goes `wait` (pulsing) while running, default green when done, `live` for Broadcaster after approval. Replace the `<small>` text with `event.summary`. Add a tiny "cached" note in the `small` text if status is cached.
2. **Scout feed:** `POSTS` array comes from `/api/scenario`. Incident title = `Incident.claim`. Velocity stays sim-driven (it looks great), but the incident `post_count` comes from Scout.
3. **Evidence board:** replace the inline `<svg>` with `<img src="/data/viral.png">` inside `.photo` (position: relative) plus absolutely positioned dashed boxes from `findings[].box_2d`:
   ```js
   // box_2d = [ymin, xmin, ymax, xmax] in 0-1000
   left = xmin/10 + '%'; top = ymin/10 + '%'; width = (xmax-xmin)/10 + '%'; height = (ymax-ymin)/10 + '%';
   ```
   Style boxes with `border: 1.6px dashed var(--water)` and the existing `.tag` number badge. Findings with `box_2d: null` use the full-image box with label "3 · match found" style like the current SVG. Keep the SVG as the fallback if the image fails to load. Fill `.finds`, the two `.side` lists, `.vword`, confidence bar width, and `.miss` rows from the Judge/Prosecutor/Defender payloads. "Draft ask" calls `/api/draft_ask` and shows the text in the existing toast (longer toast duration, 5s).
4. **Correction Lab:** build `FR` from Drafter + Society payloads. Keep `renderFramings()`. Add one line under each heat row showing the reaction quote from the group with the biggest belief drop, in `var(--muted)` 12px italic.
5. **Editor:**
   - Mic button becomes hold to talk: `pointerdown` starts `MediaRecorder`, `pointerup` stops and POSTs to `/api/voice`. Show the existing wave animation while recording.
   - Render `raw` with `filler_spans` wrapped in `.um` and `command_spans` in `.cmd` (styles already exist).
   - Fill `#enOut` / `#esOut` from `post_en` / `post_es`.
   - Apply intent: `languages` includes "es" → set `S.es = true` and update the Español toggle; `action === "approve"` → call `approve()`; `framing_hint` → select that framing.
   - Keep a "Replay demo dictation" fallback (the current scripted typing) under a small text button for when the room is loud.
6. **Feed after approval:** correction posts and Broadcaster replies come from `/api/broadcast`.
7. **Sim:** replace the hardcoded `FR[...].p` and the `0.25` Spanish multiplier with the data-driven values from Section 6.9. Clear `cache` (the in-page `Map`) whenever `FR` changes. Everything else in `sim.js` stays identical.
8. **Bring your own image:** add a small "Analyze a new image" button in the Evidence board header (`.btn.sm` style) that opens a file input, sends to `/api/analyze`, and re-renders the evidence board live. This is the unscripted moment for judges.

### Phase 4: Cache warm + demo modes (30 min)

- `scripts/warm_cache.py` runs the full pipeline once in `live` mode and saves every agent output to `cache/<agent>.json`. Run it 2-3 times and keep the best run (check the Prosecutor actually caught the sign).
- `DEMO_MODE`:
  - `replay`: everything from cache. Use if wifi dies.
  - `live`: every call real.
  - `hybrid` (default for judging): pipeline from cache, but `/api/voice`, `/api/analyze`, `/api/broadcast`, and `/api/draft_ask` are live.
- Any live call that errors or takes > 8s falls back to cache and the pill shows "cached". The demo never shows an error state.

### Phase 5: Eval (30 min, do this, it sets us apart)

- `scripts/run_eval.py`: load ~30 claims from the **LIAR** dataset on Hugging Face (statements labeled by PolitiFact). Map `pants-fire`/`false` → False, `true`/`mostly-true` → True, skip the middle labels. Balance 15/15.
- Run Prosecutor (text only) → Defender → Judge on each. Report accuracy and a confusion matrix to `cache/eval.json`.
- Show it in the UI: append "· eval 24/30" (real number) to the Judge pill's `small` text, and put it on a slide. Report the real number even if it's mediocre; explain the misses.

### Phase 6: Polish and freeze (by 4:30 PM)

- Test the full demo flow 3 times start to finish in `hybrid`.
- Test with wifi off in `replay`.
- Check phone width (judges might look on a phone) and that nothing errors in the console.
- README with: one-line pitch, track mapping table, how to run, architecture diagram (mermaid).

---

## 7. Caching rules

```python
def get_or_run(key: str, fn, mode=DEMO_MODE):
    path = CACHE / f"{key}.json"
    if mode == "replay" and path.exists():
        return load(path), "cached"
    try:
        out = with_timeout(fn, 8)
        save(path, out); return out, "done"
    except Exception:
        if path.exists(): return load(path), "cached"
        raise
```
Cache keys: `scout`, `prosecutor_<image_hash>`, `defender_<image_hash>`, `judge_<image_hash>`, `drafter`, `society_<framing>`, `editor_demo`.

---

## 8. The 3-minute demo script (build toward this)

1. **(20s)** "Fire season. A photo of fire jumping I-15 goes viral with 'Poway get out now.' It's fake. Comms has minutes."
2. **(40s)** Hit start. Feed lights up, Scout pill finishes, map starts burning. Gemini agents light up one by one.
3. **(40s)** Evidence board: boxes on the image, Judge says False with confidence, shows what's missing.
4. **(30s)** Correction Lab: three framings, persona heat map, "Action first" wins.
5. **(30s)** Hold the mic: "that's the old Arizona photo, kill it, tell Poway there's no new orders, do Spanish too." Clean posts appear, it auto-approves, blue wave spreads.
6. **(20s)** Toggle Spanish off: Escondido group stays orange. Drag the what-if slider: T+10 vs never.
7. **(10s)** "Judge scored X/30 on real PolitiFact claims." Offer: "Want to give it your own image?"

---

## 9. Scope cuts if behind (in this order)

1. Cut per-persona reaction quotes (keep group scores)
2. Cut Broadcaster reply answers (keep the posted correction)
3. Cut "Analyze a new image"
4. Cut grounded search in Prosecutor (vision only)
5. **Never cut:** the map, the evidence board with boxes, the Voiskey editor, the cache fallback

---

## 10. Inputs I (Pranav) will provide

- [ ] `GEMINI_API_KEY` and confirmed model name
- [ ] `XAI_API_KEY`, confirmed Grok model names, and any SpaceX AI / "Grok bots" track docs or SDK
- [ ] Voiskey SDK or API docs path, key, and a sample audio file
- [ ] `firebreak-ui.html` (the UI, in the project root)
