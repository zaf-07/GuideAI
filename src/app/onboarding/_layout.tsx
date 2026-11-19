import React from 'react';
import { Stack } from 'expo-router';
import { DraftProvider } from '../../screens/onboarding/draft';
import { useProfile } from '../../state/ProfileContext';

export default function OnboardingLayout() {
  const { profile } = useProfile();
  return (
    <DraftProvider initial={profile}>
      <Stack screenOptions={{ headerShown: false, animation: 'slide_from_right' }} />
    </DraftProvider>
  );
}
