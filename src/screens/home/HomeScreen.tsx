import React, { useEffect, useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Display, GlassCard, GreetingBar, Screen, Text } from '../../components';
import { Action, ActionTile, PrimaryTile } from './tiles';
import { useProfile } from '../../state/ProfileContext';
import { hasHearingTrack, hasVisionTrack, isDeafBlind } from '../../state/profile';
import { announce } from '../../lib/announce';
import { colors, spacing } from '../../theme/tokens';

const VISION_PRIMARY: Action = {
  key: 'scene',
  title: 'Describe my surroundings',
  blurb: 'Live camera narration with distances to everything around you.',
  icon: 'eye-outline',
  hint: 'Opens the live camera and starts speaking what it sees.',
};

const VISION_SECONDARY: Action[] = [
  { key: 'navigate', title: 'Walk with me', blurb: 'Turn-by-turn with kerbs, crossings and traffic', icon: 'navigate-outline' },
  { key: 'read', title: 'Read this', blurb: 'Signs, labels, menus, post', icon: 'document-text-outline' },
  { key: 'find', title: 'Find an object', blurb: 'Point and hunt for one thing', icon: 'search-outline' },
  { key: 'people', title: 'Who is here', blurb: 'Recognise saved faces', icon: 'people-outline' },
];

const HEARING_PRIMARY: Action = {
  key: 'bridge',
  title: 'Start a conversation',
  blurb: 'Your signing becomes speech, their speech becomes sign and captions.',
  icon: 'swap-horizontal-outline',
  hint: 'Opens the two-way sign language bridge.',
};

const HEARING_SECONDARY: Action[] = [
  { key: 'captions', title: 'Live captions', blurb: 'Caption the room around you', icon: 'chatbubble-ellipses-outline' },
  { key: 'practice', title: 'Practice mode', blurb: 'Check how clearly you are read', icon: 'school-outline' },
  { key: 'phrases', title: 'Saved phrases', blurb: 'Say the things you say often', icon: 'bookmark-outline' },
  { key: 'alerts', title: 'Sound alerts', blurb: 'Alarms, doorbells, your name', icon: 'notifications-outline' },
];

const DEAFBLIND_PRIMARY: Action = {
  key: 'scene',
  title: 'Feel my surroundings',
  blurb: 'Obstacles and distances as haptic patterns, with braille output.',
  icon: 'radio-outline',
  hint: 'Starts haptic scene guidance.',
};

/**
 * One home screen, three shapes. The profile decides the hero action, the
 * tiles beneath it, and the language used throughout.
 */
export function HomeScreen({ navigation }: any) {
  const { profile } = useProfile();
  const vision = hasVisionTrack(profile);
  const hearing = hasHearingTrack(profile);
  const both = isDeafBlind(profile);

  const { primary, secondary, headline } = useMemo(() => {
    if (both) {
      return {
        primary: DEAFBLIND_PRIMARY,
        secondary: [
          { key: 'navigate', title: 'Walk with me', blurb: 'Haptic turn-by-turn guidance', icon: 'navigate-outline' } as Action,
          { key: 'bridge', title: 'Tactile bridge', blurb: 'Signing to braille, both ways', icon: 'swap-horizontal-outline' } as Action,
          { key: 'read', title: 'Read this', blurb: 'Text to braille or speech', icon: 'document-text-outline' } as Action,
          { key: 'memory', title: 'Memory', blurb: 'Places and people you know', icon: 'git-network-outline' } as Action,
        ],
        headline: { lead: 'Everything,', accent: 'through touch' },
      };
    }
    if (vision) {
      return {
        primary: VISION_PRIMARY,
        secondary: VISION_SECONDARY,
        headline: { lead: 'Your eyes,', accent: 'out loud' },
      };
    }
    return {
      primary: HEARING_PRIMARY,
      secondary: HEARING_SECONDARY,
      headline: { lead: 'Speak freely,', accent: 'be understood' },
    };
  }, [vision, hearing, both]);

  useEffect(() => {
    announce(profile, `Home. ${primary.title} is the first button.`);
  }, [primary.key]);

  const open = (key: string, title: string) =>
    navigation.navigate('Feature', { key, title });

  return (
    <Screen>
      <GreetingBar
        name={profile.displayName || 'there'}
        onSettings={() => navigation.navigate('Settings')}
      />

      <View style={{ paddingTop: spacing.lg, paddingBottom: spacing.sm }}>
        <Display lead={headline.lead} accent={headline.accent} />
      </View>

      <PrimaryTile action={primary} onPress={() => open(primary.key, primary.title)} />

      <Text variant="section" style={{ marginTop: spacing.lg }}>
        More <Text variant="section" muted>for you</Text>
      </Text>

      <View style={styles.grid}>
        {secondary.map((a) => (
          <ActionTile key={a.key} action={a} onPress={() => open(a.key, a.title)} />
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
            ? 'Places you walk often, the people you meet and the objects you ask about build a private map that makes each description shorter and more useful.'
            : 'Names, signs and phrases from your conversations are linked together, so the bridge keeps your meaning across talks instead of starting fresh.'}
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
