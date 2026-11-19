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
ios/        the SwiftUI client
gateway/    FastAPI relay to a hosted vision model
models/     bundled ONNX fingerspelling classifier and PopSign vocabulary
apps/       the Expo and web app, its desktop shell, and the API behind it
docs/       design and model documentation
```

`apps/` holds the Expo and web app, the Electron shell, Shared Sight and the
API they call. They sit alongside the native client; the `legacy` branch still
marks the tree as it was before the native restructure.

The native app exists because React Native cannot reach `ARFrame.sceneDepth`,
`PHASE`, `CoreHaptics` or on-device `SFSpeechRecognizer`. The two safety rules
above are enforced for `ios/` and `gateway/`. The web app is a companion and a
demo surface: its hazard warnings come from `apps/api` over the network, so it
does not meet rule 1 and must not be relied on while walking.

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

## The web app and its API

`apps/mobile` is an Expo app that also runs in a browser; `apps/api` is the
FastAPI service it calls.

| Feature | Route | How it works |
|---|---|---|
| Hazard warnings | `POST /v1/track`, `POST /v1/vision/analyze` | A YOLO11 detector names what is in view and where: "Chair ahead, left." Position only, never distance. |
| Scene description | `POST /v1/describe` | The frame and the detections go to Gemini, then MiniMax, then Groq. If every provider fails, the answer is a sentence built from the detections. |
| Sign reading | `POST /v1/interpret-sign` | A few frames are matched against a small fixed vocabulary. Low-confidence readings are dropped. This is not full sign-language translation. |
| Assistant | `POST /v1/assistant` | One sentence in, one spoken reply out: describe, read text, "where am I", walking directions, messages, calls, timers and payments. |
| Family | `/v1/contacts`, `/v1/places` | Contacts and saved places, kept per device. "Tell Mom where I am" prepares a WhatsApp message and waits for a yes. |
| Walking directions | `POST /v1/location` | OpenStreetMap search and foot routing, spoken turn by turn. |
| Memory and Shared Sight | `/v1/recall/*`, `/v1/observations`, `/v1/alerts` | The on-device memory graph, its optional sync, and community hazard reports. |

Nothing leaves on the user's behalf — a message, a call, a payment — without
an explicit yes. Payments are simulated unless a Stripe test key is set, and a
live key is refused. Contacts, saved places and pending requests belong to the
device that created them.

```bash
npm install

# terminal 1
cd apps/api
pip install -r requirements-dev.txt
python -m pytest                       # 162 tests
GEMINI_API_KEY=your_key uvicorn main:app --port 8000

# terminal 2, from the repo root
npm run web                            # or: npm run demo, for a phone browser
```

`docker compose up --build` starts both services: the gateway on port 8000 and
`apps/api` on 8082. Run the API with uvicorn as above when using the web app
locally, because the app expects it on port 8000.

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

---

## Building without Xcode

Xcode is not required to work on the decision rules. The Command Line Tools
ship a full Swift 6 toolchain, so `ios/GuideLensCore` -- the obstacle filter,
the announcement priority policy, the motion gate and the sentence chunker --
builds and verifies locally:

```bash
cd ios/GuideLensCore
swift build
swift run GuideLensChecks     # 45 checks
```

Those rules deliberately import nothing from ARKit, PHASE, CoreHaptics or
SwiftUI. Everything that cannot be exercised without a device is kept out of
them, which is why they can be proven on a machine that cannot install Xcode,
and why the iOS app is a thin layer wiring sensors to logic already tested.

The checks are an executable rather than a test target because neither XCTest
nor swift-testing ships with the Command Line Tools. Exit status is the
contract.

`xcodebuild` and the iOS SDK need a full Xcode, so the SwiftUI client in
`ios/` is compiled in CI on a macOS runner instead -- see
`.github/workflows/ci.yml`.

**CI is not a device.** The simulator has no LiDAR, no real camera and
misleading audio timing. It can prove the app compiles and that the rules
hold; it cannot produce a single valid latency measurement, and every
acceptance criterion in the spec is a device measurement.

### If git or python stop working

macOS routes `git`, `python3` and `swift` through a stub that refuses until
the Xcode licence is accepted, even with only the Command Line Tools
installed:

```bash
sudo xcodebuild -license accept
```
