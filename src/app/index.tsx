import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { Redirect } from 'expo-router';
import { useProfile } from '../state/ProfileContext';
import { colors } from '../theme/tokens';

export default function Index() {
  const { ready, onboarded } = useProfile();
  if (!ready) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.canvas, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={colors.lime} size="large" />
      </View>
    );
  }
  return <Redirect href={onboarded ? '/home' : '/onboarding'} />;
}
