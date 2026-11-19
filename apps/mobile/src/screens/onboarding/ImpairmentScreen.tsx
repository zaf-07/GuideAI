import React from 'react';
import { View } from 'react-native';
import { router } from 'expo-router';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { Button, ChoiceCard, Display, Progress, Screen, Text } from '../../components';
import { useDraft, TOTAL_STEPS } from './draft';
import { ImpairmentId } from '../../state/profile';
import { colors, spacing } from '../../theme/tokens';

/**
 * The fork in the road. Everything after this — onboarding steps, home
 * screen, even which features exist — is decided here.
 */
export function ImpairmentScreen() {
  const { draft, set } = useDraft();
  const current: ImpairmentId | undefined = draft.impairments[0];

  const choose = (id: ImpairmentId) => set({ impairments: [id] });

  const next = () => {
    if (!current) return;
    router.push(current === 'vision' ? '/onboarding/vision' : '/onboarding/hearing');
  };

  return (
    <Screen
      footer={
        <Button
          label="Continue"
          onPress={next}
          disabled={!current}
          hint="Moves to the next setup step."
        />
      }
    >
      <Progress step={1} total={TOTAL_STEPS} />
      <Display lead="What should GuideAI" accent="make easier?" />
      <Text variant="body" muted style={{ marginBottom: spacing.md }}>
        Choose the starting point that fits you. You can change it later, and
        every mode remains available.
      </Text>

      <View style={{ gap: spacing.sm }}>
        <ChoiceCard
          title="I want to understand my surroundings"
          subtitle="Camera guidance, spoken descriptions and walking help"
          selected={current === 'vision'}
          onPress={() => choose('vision')}
          hint="Sets up the camera guidance features."
          icon={<Ionicons name="eye-outline" size={28} color={current === 'vision' ? colors.onLight : colors.lime} />}
        />
        <ChoiceCard
          title="I want to communicate without sound"
          subtitle="Sign language, large captions and flexible replies"
          selected={current === 'hearing'}
          onPress={() => choose('hearing')}
          hint="Sets up the sign language bridge."
          icon={<MaterialCommunityIcons name="hand-wave-outline" size={28} color={current === 'hearing' ? colors.onLight : colors.lime} />}
        />
        <ChoiceCard
          title="I am helping someone communicate"
          subtitle="A shared bridge between speech, text and supported signs"
          selected={current === 'communicator'}
          onPress={() => choose('communicator')}
          hint="Sets up conversation tools for a hearing person."
          icon={<MaterialCommunityIcons name="account-voice" size={28} color={current === 'communicator' ? colors.onLight : colors.lime} />}
        />
      </View>

      <Text variant="caption" faint style={{ marginTop: spacing.md }}>
        GuideAI is designed for real conversations, not diagnosis. Choose the
        experience you want to try first.
      </Text>
    </Screen>
  );
}
