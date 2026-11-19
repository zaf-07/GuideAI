# GuideAI mobile technology decision

## Decision

Use an iPhone-first hybrid architecture: Expo SDK 58 and React Native for the
application, with focused Swift modules for latency-sensitive Apple platform
features. This keeps one coherent product codebase without forcing camera,
machine-learning or peer networking through a JavaScript-only abstraction.

## Why this fits the demo and the product

The two-phone demo needs rapid UI iteration, accessible controls and reliable
native camera, speech and nearby networking. Pure SwiftUI would maximize iOS
control but slow shared product work and make a later Android client a rewrite.
Flutter would still require native bridges for the same Apple frameworks and
would discard the existing React/TypeScript work. A web app cannot provide the
required background, camera and local peer capabilities reliably.

Expo is used as a native project generator, not as a restriction to Expo Go.
Development builds include custom native modules. Native directories remain
generated artifacts; permissions and plugins are declared in `app.json`.

## Component choices

| Capability | Choice | Boundary |
|---|---|---|
| UI, onboarding, settings | React Native + TypeScript | Expo Router screens |
| Camera capture | `expo-camera` initially; AVFoundation for frame pipelines | No frame storage by default |
| Sign recognition | Vision hand/body pose + a versioned Core ML temporal model | Start with a declared, tested ASL phrase vocabulary; never call it universal translation |
| Scene understanding | Vision/Core ML, optionally depth when hardware supports it | Announce supported proximity cues; never invent exact distance |
| Speech | Apple Speech/AVSpeechSynthesizer for offline use; optional cloud adapter later | Streaming text events, interruptible output |
| Nearby conversation | Apple Network framework with Bonjour discovery | Explicit role, matching code and authenticated encryption |
| Persistence | SQLite; Keychain for secrets and pairing material | Local-first, inspectable deletion |
| Navigation | MapKit/Core Location Swift adapter | Guidance only; no “safe to cross” decision |
| Sign output | Text first; a constrained sign avatar is optional | Label vocabulary and fall back to text |

## Nearby protocol shape

1. Each phone advertises only the GuideAI service type.
2. The UI shows nearby GuideAI peers; it never joins automatically.
3. Both phones display and confirm the same short authentication code.
4. The session negotiates a version and exchanges semantic events such as
   `transcript.partial`, `transcript.final`, `sign.phrase` and `session.end`.
5. Camera or audio stays on the originating phone in the first demo; only text,
   phrase identifiers and confidence metadata cross the connection.
6. A disconnect clears ephemeral session keys and returns both clients to a
   reconnectable state.

This is intentionally not AirDrop: AirDrop is not a public application
transport. Network framework and Bonjour provide supported building blocks
while keeping the pairing experience familiar.

## Delivery order

1. Stable no-account onboarding and real permissions.
2. Two-phone discovery, pairing and bidirectional text events.
3. Speech-to-text on the blind/hearing-person phone.
4. A small, measured ASL recognition vocabulary on the signer phone.
5. Text-first conversation demo, then avatar rendering.
6. Scene narration, OCR and walking assistance as separately tested pipelines.

## Source references

- Expo SDK 58: https://docs.expo.dev/versions/v58.0.0/
- Expo Router: https://docs.expo.dev/router/introduction/
- Expo Modules API: https://docs.expo.dev/modules/overview/
- Continuous Native Generation: https://docs.expo.dev/workflow/continuous-native-generation/
- Apple Vision: https://developer.apple.com/documentation/vision
- Apple Network: https://developer.apple.com/documentation/network
- Apple Core ML: https://developer.apple.com/documentation/coreml
