import React, { useEffect, useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Display, GlassCard, GreetingBar, Screen, Text } from '../../components';
import { Action, ActionTile, PrimaryTile } from './tiles';
import { useProfile } from '../../state/ProfileContext';
import { hasHearingTrack, hasVisionTrack, isDeafBlind } from '../../state/profile';
import { announce } from '../../lib/announce';
import { colors, spacing } from '../../theme/tokens';

/**
 * Actions carry their own destination. `route` points at a working engine;
 * `key` alone falls through to the roadmap screen, so the home grid never
 * promises something the app cannot yet do.
 */
const VISION_PRIMARY: Action = {
  key: 'scene',
  title: 'Describe my surroundings',
  blurb: 'Live object tracking with distance, direction and spoken scene briefs.',
  icon: 'eye-outline',
  route: '/camera',
  hint: 'Opens the camera and starts speaking what it sees.',
};

const VISION_SECONDARY: Action[] = [
  { key: 'changed', title: 'What changed', blurb: 'Only what moved since you were last here', icon: 'git-compare-outline', route: '/hub' },
  { key: 'shared', title: 'Shared sight', blurb: 'Hazards other people reported nearby', icon: 'git-network-outline', route: '/hub' },
  { key: 'navigate', title: 'Walk with me', blurb: 'Kerbs, crossings and traffic', icon: 'navigate-outline' },
  { key: 'read', title: 'Read this', blurb: 'Signs, labels, menus, post', icon: 'document-text-outline' },
];

const HEARING_PRIMARY: Action = {
  key: 'bridge',
  title: 'Start a conversation',
  blurb: 'Your signing is spoken aloud; their speech returns as giant captions and animated signs.',
  icon: 'swap-horizontal-outline',
  route: '/bridge',
  hint: 'Opens the two-way bridge.',
};

const HEARING_SECONDARY: Action[] = [
  { key: 'translate', title: 'Sign studio', blurb: 'English ⇄ ASL with a 3D avatar', icon: 'hand-left-outline', route: '/translate' },
  { key: 'signcam', title: 'Read my signing', blurb: 'Camera reads your hands live', icon: 'videocam-outline', route: '/camera?initialMode=sign' },
  { key: 'practice', title: 'Practice mode', blurb: 'See how clearly you are read', icon: 'school-outline', route: '/record' },
  { key: 'alerts', title: 'Sound alerts', blurb: 'Alarms, doorbells, your name', icon: 'notifications-outline' },
];

const DEAFBLIND_PRIMARY: Action = {
  key: 'bridge',
  title: 'Deaf-blind bridge',
  blurb: 'Signing from one side becomes speech; speech becomes giant text and haptics on the other.',
  icon: 'people-outline',
  route: '/bridge',
  hint: 'Opens the two-way bridge.',
};

const DEAFBLIND_SECONDARY: Action[] = [
  { key: 'scene', title: 'Feel the room', blurb: 'Obstacles as haptic pulses', icon: 'radio-outline', route: '/camera' },
  { key: 'shared', title: 'Shared sight', blurb: 'Hazards reported nearby', icon: 'git-network-outline', route: '/hub' },
  { key: 'translate', title: 'Sign studio', blurb: 'English ⇄ ASL', icon: 'hand-left-outline', route: '/translate' },
  { key: 'braille', title: 'Braille output', blurb: 'Send text to a connected display', icon: 'keypad-outline' },
];

/** One home screen, three shapes — decided entirely by the profile. */
export function HomeScreen() {
  const { profile } = useProfile();
  const vision = hasVisionTrack(profile);
  const both = isDeafBlind(profile);

  const { primary, secondary, headline } = useMemo(() => {
    if (both) {
      return { primary: DEAFBLIND_PRIMARY, secondary: DEAFBLIND_SECONDARY, headline: { lead: 'Everything,', accent: 'through touch' } };
    }
    if (vision) {
      return { primary: VISION_PRIMARY, secondary: VISION_SECONDARY, headline: { lead: 'Your eyes,', accent: 'out loud' } };
    }
    return { primary: HEARING_PRIMARY, secondary: HEARING_SECONDARY, headline: { lead: 'Speak freely,', accent: 'be understood' } };
  }, [vision, both]);

  useEffect(() => {
    announce(profile, `Home. ${primary.title} is the first button.`);
  }, [primary.key]);

  const open = (a: Action) => {
    if (a.route) router.push(a.route as never);
    else router.push({ pathname: '/feature', params: { key: a.key, title: a.title } } as never);
  };

  return (
    <Screen>
      <GreetingBar
        name={profile.displayName || 'there'}
        onSettings={() => router.push('/settings')}
      />

      <View style={{ paddingTop: spacing.lg, paddingBottom: spacing.sm }}>
        <Display lead={headline.lead} accent={headline.accent} />
      </View>

      <PrimaryTile action={primary} onPress={() => open(primary)} />

      <Text variant="section" style={{ marginTop: spacing.lg }}>
        More <Text variant="section" muted>for you</Text>
      </Text>

      <View style={styles.grid}>
        {secondary.map((a) => (
          <ActionTile key={a.key} action={a} onPress={() => open(a)} />
        ))}
      </View>

      <GlassCard style={{ marginTop: spacing.lg }}>
        <View style={styles.row}>
          <Ionicons name="git-network-outline" size={22} color={colors.lime} />
          <Text variant="section" style={{ flex: 1 }}>
            What GuideAI remembers
          </Text>
        </View>
        <Text variant="body" muted>
          {vision
            ? 'Places you walk often, hazards other people reported and the objects you ask about build a private map, so each brief gets shorter and more useful.'
            : 'Names, signs and phrases from your conversations stay linked, so the bridge keeps your meaning across talks instead of starting fresh.'}
        </Text>
        <Text variant="caption" faint>
          Memory graph · on this device · {profile.localOnlyMemory ? 'not synced' : 'synced'}
        </Text>
      </GlassCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
});
