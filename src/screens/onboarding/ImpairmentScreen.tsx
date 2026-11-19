import React from 'react';
import { View } from 'react-native';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { Button, ChoiceCard, Display, Progress, Screen, Text } from '../../components';
import { useDraft, TOTAL_STEPS } from './draft';
import { ImpairmentId } from '../../state/profile';
import { colors, spacing } from '../../theme/tokens';

/**
 * The fork in the road. Everything after this — onboarding steps, home
 * screen, even which features exist — is decided here.
 */
export function ImpairmentScreen({ navigation }: any) {
  const { draft, set } = useDraft();
  const current: ImpairmentId | undefined = draft.impairments[0];

  const choose = (id: ImpairmentId) => set({ impairments: [id] });

  const next = () => {
    if (!current) return;
    navigation.navigate(current === 'hearing' ? 'HearingSetup' : 'VisionSetup');
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
      <Display lead="Let's set up" accent="for you" />
      <Text variant="body" muted style={{ marginBottom: spacing.md }}>
        Pick what fits you best. This shapes the whole app — you can change it
        later in Settings.
      </Text>

      <View style={{ gap: spacing.sm }}>
        <ChoiceCard
          title="Blind or low vision"
          subtitle="Live scene description, obstacle and traffic guidance"
          selected={current === 'vision'}
          onPress={() => choose('vision')}
          hint="Sets up the camera guidance features."
          icon={<Ionicons name="eye-outline" size={28} color={current === 'vision' ? colors.onLight : colors.lime} />}
        />
        <ChoiceCard
          title="Deaf or hard of hearing"
          subtitle="Two-way sign language and speech translation"
          selected={current === 'hearing'}
          onPress={() => choose('hearing')}
          hint="Sets up the sign language bridge."
          icon={<MaterialCommunityIcons name="hand-wave-outline" size={28} color={current === 'hearing' ? colors.onLight : colors.lime} />}
        />
        <ChoiceCard
          title="Deaf-blind"
          subtitle="Haptic guidance, braille output, tactile signing support"
          selected={current === 'deafblind'}
          onPress={() => choose('deafblind')}
          hint="Sets up both tracks with touch as the main channel."
          icon={<MaterialCommunityIcons name="vibrate" size={28} color={current === 'deafblind' ? colors.onLight : colors.lime} />}
        />
      </View>

      <Text variant="caption" faint style={{ marginTop: spacing.md }}>
        Not sure? Choose the closest one. Nothing here is locked in.
      </Text>
    </Screen>
  );
}
