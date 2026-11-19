# GuideLens

A native iOS accessibility app that commits to **one purpose per user**, chosen
once during onboarding and never shown as a menu again.

- A user with vision impairment gets an app that is only navigation and voice
  conversation.
- A user with hearing impairment gets an app that is only sign-language and
  speech communication.
- A user with both gets a combined haptic-and-large-text surface.

After onboarding there is a single full-screen surface with no tab bar, no
mode switcher and no settings screen. A phone held by someone who cannot see
it, or glanced at mid-conversation by someone who cannot hear, has room for
exactly one job.

---

## Safety

**This is assistive companion technology. It is not a substitute for a white
cane, a guide dog, orientation-and-mobility training, or any medical device.**

Two rules are structural, not stylistic, and they constrain every line of
code in this repository:

1. **No network call is ever in the safety loop.** Obstacle detection,
   distance and collision warning run entirely on the device. If the network
   dies mid-walk, safety behaviour does not change. The hosted model produces
   *descriptions*; it never produces *warnings*.

2. **The app never asserts safety.** It may say "pole, two meters, ten
   o'clock." It may never say "path is clear", "safe to proceed", "nothing
   ahead", or anything a user could act on as an all-clear. **Absence of
   detection is not detection of absence.** This is enforced by a test that
   fails the build: `gateway/tests/test_safety_language.py`.

---

## Layout

```
ios/        the SwiftUI client — the only client
gateway/    FastAPI relay to a hosted vision model
models/     bundled ONNX fingerspelling classifier and PopSign vocabulary
docs/       design and model documentation
```

The React Native app, the Electron desktop build, the Uni-Sign research
adapter, the Groq client and the Shared Sight hazard-reporting feature were
removed from `main`. Nothing was destroyed: all of it is on the **`legacy`**
branch, at the commit before the surgery.

React Native was removed because it cannot reach `ARFrame.sceneDepth`,
`PHASE`, `CoreHaptics` or on-device `SFSpeechRecognizer`. Those four APIs are
the entire product.

Shared Sight was removed because community hazard reporting needs a map, a
list, a submission form and a moderation story — four screens that the
single-surface rule has no room for. It is worth revisiting once the core app
has real users.

---

## The gateway

One WebSocket endpoint. The client opens it when the vision surface loads and
keeps it warm, because per-frame HTTP would spend 150–300 ms on DNS, TLS and
connection setup every single frame.

```
GET  /health          configuration and model IDs
WS   /v1/narrate      frames in, spoken fragments out
```

```
client -> {"type": "narrate",  "frame": "<base64 jpeg>"}
          {"type": "question", "frame": "<base64 jpeg>", "text": "..."}
          {"type": "ping"}
server -> {"type": "delta", "text": "..."}     streamed fragment
          {"type": "done",  "skipped": bool}   end of one reply
          {"type": "error", "message": "...", "fatal": bool}
```

Replies stream. Each delta is relayed the instant it arrives so the client can
speak sentence by sentence instead of waiting for completion — the difference
between 1.5 s and about 400 ms of perceived latency.

Most frames should produce `{"done": skipped: true}` and no speech at all.
Constant chatter is the top complaint about assistive vision apps, so the
narration prompt answers `SKIP` whenever a frame holds nothing worth saying.

**The API key never reaches the phone.** Every client proves a 256-bit secret
whose first 128 bits are its public device ID, so the server verifies the
whole secret without storing anything — no enrolment table, and no way for one
client to claim another's identity. Request frequency is bounded by layered
per-session, per-peer and process-wide limits; *spend* is bounded separately
by a rolling hourly token budget per device, because a client within its rate
limit can still burn credits indefinitely.

### Running it

```bash
cp .env.example .env     # add NEBIUS_API_KEY; never commit it
docker compose up --build
curl http://localhost:8000/health
```

```bash
cd gateway
pip install -r requirements-dev.txt
pytest -q                # 76 tests
```

The in-process rate limits and token budget assume **one worker**. A
multi-worker or internet-facing deployment must enforce matching limits at a
shared gateway, or each worker will allow the full budget by itself.

---

## The iOS app

`ios/` opens in Xcode 16+. A physical device is required: the simulator has no
LiDAR, no real camera, and misleading audio timing, so no measurement taken
there means anything.

Build and test on device, and treat the latency targets as acceptance
criteria rather than aspirations.

---

## Attribution

Parts of this repository originate from GuideLens
(https://github.com/k1lst1x/GuideLens), MIT licensed; the original notice is
kept at `LICENSE-GuideLens`, and `THIRD_PARTY_NOTICES.md` lists upstream
models and datasets.
