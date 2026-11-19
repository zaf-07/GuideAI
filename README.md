# GuideAI

GuideAI is an iPhone-first accessibility companion with three entry modes:

- blind or low-vision: spoken setup, scene description, reading and walking assistance;
- Deaf or hard-of-hearing: signing to speech plus speech to text or a sign avatar;
- conversation partner: a hearing person can communicate with a Deaf signer without knowing sign language.

There is no account gate. The first launch stores an accessibility profile on
the phone, and the selected mode can be changed later in Settings.

## Current implementation

The repository contains a working Expo SDK 58 application shell with Expo
Router, persistent local onboarding, the three profiles, adaptive home and
settings screens, real iOS camera/microphone/location permission requests,
speech output and haptic support. The production iOS JavaScript bundle builds
successfully.

Scene understanding, sign recognition, the sign avatar and the encrypted
nearby two-phone session are intentionally labelled as pipelines still to be
implemented; the UI does not pretend that placeholder output is real.

## Technology direction

- React Native + TypeScript + Expo SDK 58 for product UI and iteration.
- Expo Router for file-based navigation under `src/app`.
- Expo Modules API for Swift code that needs Apple frameworks.
- AVFoundation + Vision/Core ML for camera and on-device inference.
- Apple Network framework + Bonjour for nearby discovery and an encrypted,
  paired conversation channel. A matching short code prevents accidental
  connection to another nearby user.
- Speech, SQLite, Location and haptics for supporting accessibility tools.

The full decision and rejected alternatives are in
[`docs/TECHNOLOGY_DECISION.md`](docs/TECHNOLOGY_DECISION.md).

## Run and verify

```bash
npm install --legacy-peer-deps
npm run typecheck
npm run lint
npx expo-doctor
npx expo start
```

A real-device development build needs the Xcode license accepted and CocoaPods
installed, then:

```bash
npx expo run:ios --device
```

The generated `ios/` and `android/` directories are ignored. Native settings
belong in `app.json` or an Expo config plugin so Continuous Native Generation
can recreate them safely.

## Layout

```text
src/app/                    Expo Router routes
src/screens/onboarding/     mode, preferences, permissions and confirmation
src/screens/home/           profile-aware home
src/state/                  local accessibility profile and persistence
src/lib/announce.ts         non-duplicating speech / VoiceOver announcements
src/components/             accessible reusable UI
```

## Safety and privacy rules

- GuideAI must never claim a road is safe to cross.
- Camera frames are not stored by default.
- A cloud-backed feature must identify the service before data is sent.
- Nearby conversations require explicit confirmation on both phones.
- Memory starts local-only and must remain inspectable and deletable.
