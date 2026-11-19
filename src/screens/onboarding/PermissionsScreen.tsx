import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Button, Display, GlassCard, Progress, Screen, Text } from '../../components';
import { TOTAL_STEPS, useDraft } from './draft';
import { hasHearingTrack, hasVisionTrack } from '../../state/profile';
import { colors, radius, spacing } from '../../theme/tokens';

interface Perm {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  why: string;
}

/** Step 3: explain every sensor before the system prompts appear. */
export function PermissionsScreen({ navigation }: any) {
  const { draft } = useDraft();
  const perms: Perm[] = [];

  if (hasVisionTrack(draft)) {
    perms.push(
      { icon: 'camera-outline', title: 'Camera', why: 'Reads the scene in front of you and measures how far things are.' },
      { icon: 'navigate-outline', title: 'Location & motion', why: 'Keeps you on the path, and knows which way you are facing at a crossing.' },
    );
  }
  if (hasHearingTrack(draft)) {
    perms.push(
      { icon: 'camera-outline', title: 'Camera', why: 'Watches your hands so your signing can be translated.' },
      { icon: 'mic-outline', title: 'Microphone', why: 'Hears the other person so their speech becomes sign and captions.' },
    );
  }
  // De-duplicate camera when both tracks are on.
  const unique = perms.filter((p, i) => perms.findIndex((q) => q.title === p.title) === i);

  return (
    <Screen
      footer={
        <View style={{ gap: spacing.sm }}>
          <Button
            label="Allow access"
            onPress={() => navigation.navigate('Ready')}
            hint="iOS will ask you about each one in turn."
          />
          <Button label="Not now" tone="ghost" onPress={() => navigation.navigate('Ready')} />
        </View>
      }
    >
      <Progress step={3} total={TOTAL_STEPS} />
      <Display lead="What GuideAI" accent="needs access to" />
      <Text variant="body" muted style={{ marginBottom: spacing.md }}>
        Everything below is processed on your phone. Nothing is uploaded, and
        no video is ever stored.
      </Text>

      <View style={{ gap: spacing.sm }}>
        {unique.map((p) => (
          <GlassCard key={p.title} style={styles.row}>
            <View style={styles.icon}>
              <Ionicons name={p.icon} size={24} color={colors.lime} />
            </View>
            <View style={{ flex: 1, gap: 4 }}>
              <Text variant="section">{p.title}</Text>
              <Text variant="body" muted>
                {p.why}
              </Text>
            </View>
          </GlassCard>
        ))}
      </View>

      <GlassCard style={{ marginTop: spacing.md }}>
        <View style={styles.row}>
          <View style={styles.icon}>
            <Ionicons name="lock-closed-outline" size={24} color={colors.lime} />
          </View>
          <View style={{ flex: 1, gap: 4 }}>
            <Text variant="section">Private memory</Text>
            <Text variant="body" muted>
              GuideAI remembers places, people and conversations so it can say
              "your usual crossing" instead of starting from zero. That memory
              lives on this device.
            </Text>
          </View>
        </View>
      </GlassCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  icon: {
    width: 48,
    height: 48,
    borderRadius: radius.md,
    backgroundColor: 'rgba(185,240,91,0.12)',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
