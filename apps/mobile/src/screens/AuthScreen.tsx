import React, { useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Button, Display, GlassCard, Screen, Text } from '../components';
import { useProfile } from '../state/ProfileContext';
import { colors, HIT, radius, spacing } from '../theme/tokens';

/**
 * Entry point. Kept to one field and one very large button: this screen is
 * often the first thing a new blind user touches with VoiceOver on.
 */
export function AuthScreen() {
  const { signIn } = useProfile();
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  const go = async (displayName: string) => {
    setBusy(true);
    try {
      await signIn(displayName.trim() || 'Friend');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen
      footer={
        <View style={styles.footer}>
          <Button
            label="Continue"
            busy={busy}
            onPress={() => go(name)}
            hint="Creates your GuideAI profile and starts setup."
          />
          <Button
            label="Continue with Apple"
            tone="glass"
            onPress={() => go(name)}
            icon={<Ionicons name="logo-apple" size={22} color={colors.text} />}
            hint="Signs you in with your Apple ID."
          />
        </View>
      }
    >
      <View style={styles.hero}>
        <View style={styles.mark}>
          <Ionicons name="eye-outline" size={34} color={colors.onLight} />
        </View>
      </View>

      <Display lead="See more," accent="say more" />
      <Text variant="body" muted style={styles.sub}>
        GuideAI describes the world around you, and turns sign language into
        speech both ways — on device, in real time.
      </Text>

      <GlassCard>
        <Text variant="label" muted>
          What should we call you?
        </Text>
        <TextInput
          value={name}
          onChangeText={setName}
          placeholder="Your name"
          placeholderTextColor={colors.textFaint}
          style={styles.input}
          accessibilityLabel="Your name"
          returnKeyType="done"
          onSubmitEditing={() => go(name)}
        />
      </GlassCard>

      <Text variant="caption" faint>
        Nothing leaves your phone unless you turn on sync. You can change that
        any time in Settings.
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { paddingTop: spacing.xxl, paddingBottom: spacing.lg },
  mark: {
    width: 76,
    height: 76,
    borderRadius: 38,
    backgroundColor: colors.lime,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sub: { marginBottom: spacing.md },
  input: {
    minHeight: HIT,
    color: colors.text,
    fontSize: 20,
    borderRadius: radius.md,
    backgroundColor: 'rgba(0,0,0,0.22)',
    paddingHorizontal: spacing.md,
  },
  footer: { gap: spacing.sm },
});
