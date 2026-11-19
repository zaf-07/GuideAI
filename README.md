# GuideAI

A real-time, privacy-first accessibility app for blind, low-vision, deaf,
hard-of-hearing and deaf-blind people. Two engines, one app:

- **Vision** — the camera describes what is around you, with distances and
  bearings, and guides you through real traffic.
- **Bridge** — two-way translation between sign language and spoken English.

Both are backed by a relationship-based memory graph, so the app remembers
places, people and conversations instead of starting from zero every time.

## Status

This commit contains the **shell**: design system, authentication entry,
the branching onboarding flow, the profile store, the adaptive home screen
and settings. The camera, sign-recognition and memory engines are not wired
yet — each feature screen states exactly which pipeline belongs there.

## Running it

```bash
npm install
npx expo start       # scan the QR code with Expo Go on your iPhone
```

A native build (needed once the camera engine lands) uses EAS:

```bash
npx eas build --platform ios --profile development
```

## How the app reshapes itself

`src/state/profile.ts` defines the accessibility profile. One answer in
onboarding — vision, hearing or deaf-blind — decides:

| | Vision | Hearing | Deaf-blind |
|---|---|---|---|
| Onboarding step 2 | sight level, narration style, speech rate | hearing level, sign language, captions | both, with touch as the main channel |
| Home hero action | Describe my surroundings | Start a conversation | Feel my surroundings |
| Home tiles | navigate, read, find, faces | captions, practice, phrases, alerts | navigate, tactile bridge, read, memory |
| Announcements | spoken via `expo-speech` | visual + captions only | haptic patterns |

`RootNavigator` picks one of three mutually exclusive stacks (auth →
onboarding → app) and keys the app stack on the profile, so completing or
re-running onboarding remounts the tree rather than leaving screens from the
previous profile behind.

Settings → **Change my profile** clears the completion stamp, which drops the
user straight back into onboarding with their current answers pre-filled.

## Layout

```
src/
  theme/tokens.ts        colours, radii, type scale, 64pt minimum hit size
  state/profile.ts       profile type + track predicates
  state/ProfileContext   persistence (AsyncStorage) and the onboarding gate
  lib/announce.ts        single announcement path: speech / haptics / VoiceOver
  components/            Screen, Text + Display, Button, Card, Progress, Header
  screens/
    AuthScreen
    onboarding/          Impairment → Vision|Hearing setup → Permissions → Ready
    home/HomeScreen      one screen, three shapes
    FeatureScreen        per-feature placeholder naming the missing engine
    SettingsScreen
  navigation/RootNavigator
```

## Accessibility rules this codebase follows

- Every interactive element is at least 64pt tall and carries an explicit
  `accessibilityLabel`; hints are full sentences.
- Text scales to 2.4× system size (1.8× for display headings).
- Nothing is conveyed by colour alone — selection also changes shape and fill.
- Announcements go through `announce()` only, so VoiceOver users never hear
  the same line twice at two different speech rates.
