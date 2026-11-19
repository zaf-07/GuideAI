import React from 'react';
import { router } from 'expo-router';
import { StyleSheet, Switch, View } from 'react-native';
import { Button, ChoiceCard, Chip, Display, GlassCard, Progress, Screen, Text } from '../../components';
import { TOTAL_STEPS, useDraft } from './draft';
import { HearingLevel, SignLanguage } from '../../state/profile';
import { colors, spacing } from '../../theme/tokens';

const LEVELS: { id: HearingLevel; title: string; subtitle: string }[] = [
  { id: 'hard_of_hearing', title: 'Hard of hearing', subtitle: 'I use hearing aids or lip-read in quiet rooms' },
  { id: 'deaf', title: 'Deaf', subtitle: 'I sign and read captions' },
  { id: 'profoundly_deaf', title: 'Profoundly deaf', subtitle: 'Sign language is my first language' },
];

const LANGS: SignLanguage[] = ['ASL', 'BSL', 'ISL', 'LSF', 'other'];

/** Step 2 for the hearing track: level, signing language, caption style. */
export function HearingSetupScreen() {
  const { draft, set } = useDraft();

  return (
    <Screen
      footer={
        <Button
          label="Continue"
          disabled={!draft.hearingLevel || !draft.signLanguage}
          onPress={() => router.push('/onboarding/permissions')}
        />
      }
    >
      <Progress step={2} total={TOTAL_STEPS} />
      <Display lead="How do you" accent="communicate?" />
      <Text variant="body" muted style={{ marginBottom: spacing.md }}>
        The bridge translates signing into spoken English, and the other
        person's speech back into sign.
      </Text>

      <View style={{ gap: spacing.sm }}>
        {LEVELS.map((l) => (
          <ChoiceCard
            key={l.id}
            title={l.title}
            subtitle={l.subtitle}
            selected={draft.hearingLevel === l.id}
            onPress={() => set({ hearingLevel: l.id })}
          />
        ))}
      </View>

      <GlassCard style={{ marginTop: spacing.md }}>
        <Text variant="section">Your sign language</Text>
        <View style={styles.chips}>
          {LANGS.map((l) => (
            <Chip
              key={l}
              label={l === 'other' ? 'Other' : l}
              active={draft.signLanguage === l}
              onPress={() => set({ signLanguage: l })}
            />
          ))}
        </View>
        <Text variant="caption" faint>
          Recognition models are downloaded per language and run on device.
        </Text>
      </GlassCard>

      <GlassCard>
        <View style={styles.rowBetween}>
          <View style={{ flex: 1, gap: 4 }}>
            <Text variant="section">Large captions</Text>
            <Text variant="caption" faint>
              High-contrast captions for everything the other person says.
            </Text>
          </View>
          <Switch
            value={draft.captions}
            onValueChange={(v) => set({ captions: v })}
            trackColor={{ true: colors.lime, false: 'rgba(255,255,255,0.2)' }}
            accessibilityLabel="Large captions"
          />
        </View>
      </GlassCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginVertical: spacing.sm },
  rowBetween: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
});
