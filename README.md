# GuideAI

A real-time, privacy-first AI vision and sign language ecosystem for blind,
visually impaired, deaf and deaf-blind people.

GuideAI merges two codebases:

- **GuideLens** (https://github.com/k1lst1x/GuideLens, MIT) — the working
  engine room: on-device YOLOX/YOLO11 object detection and BoT-SORT tracking,
  depth and obstacle estimation, the ASL recognition and translation stack,
  Shared Sight campus memory, the FastAPI inference gateway, the Electron
  desktop shell and the native SwiftUI VisionMate client.
- **GuideAI shell** — an accessibility-profile-driven app around it:
  authentication, a branching onboarding flow, and a home screen that rebuilds
  itself around whether the user is blind, deaf or deaf-blind.

> **Safety:** assistive companion technology. Not a substitute for a white
> cane, guide dog, orientation training, mobility aids or medical devices.

## Repository layout

```
apps/mobile      Expo SDK 58 + expo-router app for iOS, Android and web
apps/api         FastAPI inference service (YOLO, depth, SLAM, sign decoding)
apps/desktop     Electron wrapper around the web build
VisionMate/      Native SwiftUI iOS 17 client (Apple frameworks only)
docs/            Device testing, sign-language model and dataset documentation
```

## Running the app

```bash
npm install
npm run dev          # Expo dev server
npm run tunnel       # dev server over https, for testing on a phone
npm run web          # browser fallback
npm run typecheck
npm run test:unit    # engine and memory-graph tests
```

Run these from the repository root. Starting Expo from the root *directly*
(`npx expo start`) makes it treat the workspace root as the project and fail
looking for an `App.tsx` that lives in `apps/mobile`; the scripts above enter
the app directory first.

Because GuideAI bundles ONNX Runtime native code, use an Expo **development
build** rather than Expo Go:

```bash
npx eas-cli build --platform ios --profile development
```

Point the app at a backend before starting Expo:

```bash
cp .env.example .env     # add a rotated GROQ_API_KEY; never commit it
docker compose up --build
export EXPO_PUBLIC_API_URL=http://192.168.1.25:8000   # LAN address, not localhost
```

## How the app reshapes itself

`apps/mobile/src/state/profile.ts` holds the accessibility profile. One answer
in onboarding — blind/low vision, deaf/hard of hearing, or deaf-blind —
decides what the rest of the app is:

| | Blind / low vision | Deaf / HoH | Deaf-blind |
|---|---|---|---|
| Onboarding step 2 | sight level, narration style, speech rate | hearing level, sign language, captions | both, with touch as the main channel |
| Hero action | Describe my surroundings → `/camera` | Start a conversation → `/bridge` | Deaf-blind bridge → `/bridge` |
| Tiles | What changed, Shared Sight, walk with me, read this | Sign studio, read my signing, practice, alerts | feel the room, shared sight, sign studio, braille |
| Announcements | spoken via `expo-speech` | captions and visuals only | haptic patterns |

`apps/mobile/app/index.tsx` is the gate: signed out → `/auth`, signed in but
not set up → `/onboarding/impairment`, otherwise the tailored home. Settings →
**Change my profile** clears the completion stamp and runs the branch again
with the current answers pre-filled.

Tiles whose engine exists route straight into the GuideLens surfaces
(`/camera`, `/bridge`, `/translate`, `/hub`, `/record`). Tiles whose engine is
still missing route to `/feature`, which names the pipeline that belongs
there rather than pretending to work.

## Memory

GuideAI remembers in a graph: nodes are things worth remembering (places,
people, objects, hazards, conversation turns), edges are how they relate
(`co_occurred`, `located_in`, `said_by`, `refers_to`). Recall returns a match
*with the context around it*, so a brief can say "the bin, by your front door,
where you also pass the postbox".

The on-device graph is always written and works offline. Sync through
[Supermemory](https://supermemory.ai) is opt-in via Settings → **Keep memory
on this device**, and goes through `apps/api` so the Supermemory key never
ships in the app bundle. The namespace is derived from the device ID the API
has already verified, which is what isolates one device's memories from
another's.

```bash
SUPERMEMORY_API_KEY=sm_...     # blank = on-device only, everything still works
```

See [docs/MEMORY.md](docs/MEMORY.md) for the model, the capture rules and the
API contract.

## Mobile source map

```
app/                 expo-router routes (shell + GuideLens surfaces)
components/          AssistantHub, HandTracker, SignPlayer, LiveSceneMap, RoomSketchMap
src/vision.ts        scene briefs, endpoint security, request pacing
src/detector.*       YOLOX/YOLO11 via ONNX Runtime (native + web backends)
src/asl*             fingerspelling, word transformer, gloss translation, sign poses
src/campusMemory.ts  Shared Sight observations and Personal Recall
src/sightIdentity.ts device secret and stable public ID
src/memory/          the memory graph: model, recall, capture, Supermemory sync
src/state/           accessibility profile + persistence
src/theme/           design tokens shared by shell and engine screens
src/screens/         auth, onboarding, adaptive home, settings, roadmap
```

## Accessibility rules this codebase follows

- Every interactive element is at least 64pt tall with an explicit
  `accessibilityLabel`; hints are full sentences.
- Text scales to 2.4× system size (1.8× for display headings).
- Nothing is conveyed by colour alone — selection changes shape and fill too.
- All announcements go through `src/lib/announce.ts`, so VoiceOver users never
  hear the same line twice at two different speech rates.

## Attribution

GuideLens is MIT licensed, © 2026 saint. The original notice is kept at
`LICENSE-GuideLens`, and `THIRD_PARTY_NOTICES.md` lists upstream models and
datasets. GuideAI's own additions are MIT licensed under `LICENSE`.
