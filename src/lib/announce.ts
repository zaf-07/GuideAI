import { AccessibilityInfo, Platform } from 'react-native';
import * as Speech from 'expo-speech';
import * as Haptics from 'expo-haptics';
import { Profile, hasVisionTrack, isDeafBlind } from '../state/profile';

/**
 * One announcement path for the whole app.
 *  - Blind / low-vision users hear it spoken at their chosen rate.
 *  - Deaf-blind users get a haptic pattern instead of speech; captions and
 *    (later) a braille-display route carry the text.
 *  - Everyone also gets it on the platform screen-reader queue, so VoiceOver
 *    users never hear it twice at different rates.
 */
export function announce(profile: Profile, message: string, opts?: { urgent?: boolean }) {
  if (isDeafBlind(profile)) {
    if (profile.haptics) {
      Haptics.notificationAsync(
        opts?.urgent
          ? Haptics.NotificationFeedbackType.Warning
          : Haptics.NotificationFeedbackType.Success,
      ).catch(() => {});
    }
    return;
  }

  if (hasVisionTrack(profile)) {
    if (opts?.urgent) Speech.stop();
    Speech.speak(message, {
      rate: profile.speechRate,
      pitch: 1,
      language: 'en-US',
    });
  }

  if (Platform.OS !== 'web') {
    AccessibilityInfo.announceForAccessibility(message);
  }
}

export function stopSpeaking() {
  Speech.stop();
}
