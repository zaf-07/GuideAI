import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Button, Display, GlassCard, RoundButton, Screen, Text } from '../components';
import { useProfile } from '../state/ProfileContext';
import { announce, stopSpeaking } from '../lib/announce';
import { colors, radius, spacing } from '../theme/tokens';

/**
 * Placeholder surface for a feature whose engine is not wired yet. It states
 * plainly what will run here, so the flow can be walked end to end without
 * pretending the camera pipeline exists.
 */
const COPY: Record<string, { accent: string; what: string; needs: string[] }> = {
  scene: {
    accent: 'live scene',
    what: 'The rear camera streams into an on-device detection model. Every object gets a label, a bearing and a distance, and the important ones are spoken in priority order.',
    needs: ['Camera frames at 30fps', 'Depth from LiDAR or stereo estimate', 'Object detection + depth fusion', 'Speech queue with interruption'],
  },
  navigate: {
    accent: 'navigation',
    what: 'Route guidance built for walking, not driving: kerbs, crossings, pavement edges, traffic direction and the moment it is safe to step out.',
    needs: ['Location + heading', 'Pedestrian routing', 'Crossing and signal detection', 'Haptic proximity channel'],
  },
  read: { accent: 'reading', what: 'Text in the camera view is read aloud in reading order, with layout preserved for menus, forms and signs.', needs: ['On-device OCR', 'Layout analysis', 'Language detection'] },
  find: { accent: 'object search', what: 'Name one thing and sweep the camera; the pitch of the tone rises as it enters the frame.', needs: ['Open-vocabulary detection', 'Audio pitch feedback'] },
  people: { accent: 'faces', what: 'People you have saved are announced by name when they come into view. Face data never leaves the phone.', needs: ['On-device face embeddings', 'Encrypted local store'] },
  bridge: {
    accent: 'the bridge',
    what: 'Two directions at once: your signing is tracked and spoken aloud, while the other person\'s speech is transcribed and rendered as sign.',
    needs: ['Hand and body pose tracking', 'Sign language recognition model', 'Speech recognition + synthesis', 'Sign avatar renderer'],
  },
  captions: { accent: 'captions', what: 'Everything said near you becomes large, high-contrast text with speaker separation.', needs: ['Streaming speech recognition', 'Speaker diarisation'] },
  practice: { accent: 'practice', what: 'Sign into the camera and see exactly how the model read you, so you can tell where it struggles.', needs: ['Recognition confidence feedback'] },
  phrases: { accent: 'phrases', what: 'Your common phrases, one tap from being spoken aloud in your own saved voice.', needs: ['Phrase store', 'Voice synthesis'] },
  alerts: { accent: 'alerts', what: 'Doorbells, alarms, sirens and your name trigger a distinct vibration pattern.', needs: ['Ambient sound classification', 'Haptic patterns'] },
  memory: { accent: 'memory', what: 'The graph of places, people and conversations GuideAI has built, which you can browse, correct and delete.', needs: ['Relationship-based memory store', 'Per-node delete'] },
};

export function FeatureScreen({ route, navigation }: any) {
  const { key, title } = route.params as { key: string; title: string };
  const { profile } = useProfile();
  const copy = COPY[key] ?? { accent: 'this feature', what: 'Coming soon.', needs: [] };

  useEffect(() => {
    announce(profile, `${title}. ${copy.what}`);
    return () => stopSpeaking();
  }, [key]);

  return (
    <Screen
      footer={
        <Button label="Back to home" tone="glass" onPress={() => navigation.goBack()} />
      }
    >
      <View style={styles.bar}>
        <RoundButton icon="chevron-back" label="Back" onPress={() => navigation.goBack()} />
      </View>

      <Display lead={title} accent={copy.accent} />

      <GlassCard style={{ marginTop: spacing.md }}>
        <Text variant="body">{copy.what}</Text>
      </GlassCard>

      {copy.needs.length ? (
        <GlassCard>
          <Text variant="section">Engine not wired yet</Text>
          <Text variant="caption" faint>
            This screen is the finished flow around a pipeline still to be built:
          </Text>
          <View style={{ gap: spacing.xs, marginTop: spacing.sm }}>
            {copy.needs.map((n) => (
              <View key={n} style={styles.row}>
                <Ionicons name="ellipse-outline" size={10} color={colors.textFaint} />
                <Text variant="body" muted style={{ flex: 1 }}>
                  {n}
                </Text>
              </View>
            ))}
          </View>
        </GlassCard>
      ) : null}

      <View style={styles.viewfinder} accessible accessibilityLabel="Camera preview placeholder">
        <Ionicons name="scan-outline" size={44} color={colors.textFaint} />
        <Text variant="caption" faint>
          Camera preview appears here
        </Text>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: 'row', paddingTop: spacing.sm, paddingBottom: spacing.md },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  viewfinder: {
    marginTop: spacing.md,
    height: 220,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.glassBorder,
    backgroundColor: 'rgba(0,0,0,0.25)',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
});
