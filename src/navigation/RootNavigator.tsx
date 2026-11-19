import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { NavigationContainer, DarkTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { AuthScreen } from '../screens/AuthScreen';
import { ImpairmentScreen } from '../screens/onboarding/ImpairmentScreen';
import { VisionSetupScreen } from '../screens/onboarding/VisionSetupScreen';
import { HearingSetupScreen } from '../screens/onboarding/HearingSetupScreen';
import { PermissionsScreen } from '../screens/onboarding/PermissionsScreen';
import { ReadyScreen } from '../screens/onboarding/ReadyScreen';
import { DraftProvider } from '../screens/onboarding/draft';
import { HomeScreen } from '../screens/home/HomeScreen';
import { FeatureScreen } from '../screens/FeatureScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { useProfile } from '../state/ProfileContext';
import { colors } from '../theme/tokens';

const Stack = createNativeStackNavigator();

const navTheme = {
  ...DarkTheme,
  colors: { ...DarkTheme.colors, background: colors.canvas, card: colors.canvas, text: colors.text },
};

const screenOptions = { headerShown: false, animation: 'slide_from_right' as const };

function OnboardingStack() {
  const { profile } = useProfile();
  return (
    <DraftProvider initial={profile}>
      <Stack.Navigator screenOptions={screenOptions}>
        <Stack.Screen name="Impairment" component={ImpairmentScreen} />
        <Stack.Screen name="VisionSetup" component={VisionSetupScreen} />
        <Stack.Screen name="HearingSetup" component={HearingSetupScreen} />
        <Stack.Screen name="Permissions" component={PermissionsScreen} />
        <Stack.Screen name="Ready" component={ReadyScreen} />
      </Stack.Navigator>
    </DraftProvider>
  );
}

function AppStack() {
  return (
    <Stack.Navigator screenOptions={screenOptions}>
      <Stack.Screen name="Home" component={HomeScreen} />
      <Stack.Screen name="Feature" component={FeatureScreen} />
      <Stack.Screen name="Settings" component={SettingsScreen} />
    </Stack.Navigator>
  );
}

/**
 * Three mutually exclusive worlds. Because the whole tree is keyed on the
 * profile, finishing (or re-running) onboarding remounts the app rather than
 * leaving stale screens from the previous profile behind.
 */
export function RootNavigator() {
  const { ready, signedIn, onboarded, profile } = useProfile();

  if (!ready) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.canvas, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={colors.lime} size="large" />
      </View>
    );
  }

  return (
    <NavigationContainer theme={navTheme}>
      {!signedIn ? (
        <Stack.Navigator screenOptions={screenOptions}>
          <Stack.Screen name="Auth" component={AuthScreen} />
        </Stack.Navigator>
      ) : !onboarded ? (
        <OnboardingStack />
      ) : (
        <React.Fragment key={profile.impairments.join('-')}>
          <AppStack />
        </React.Fragment>
      )}
    </NavigationContainer>
  );
}
