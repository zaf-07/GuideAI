import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { DEFAULT_PROFILE, Profile } from './profile';

const KEY = 'guideai.profile.v1';
const AUTH_KEY = 'guideai.auth.v1';

interface Ctx {
  /** null until storage has been read. */
  ready: boolean;
  signedIn: boolean;
  profile: Profile;
  /** True once onboarding completed — drives the root navigator swap. */
  onboarded: boolean;
  signIn: (displayName: string) => Promise<void>;
  signOut: () => Promise<void>;
  patch: (p: Partial<Profile>) => Promise<void>;
  completeOnboarding: (p: Partial<Profile>) => Promise<void>;
  /** Sends the user back through the impairment branch from Settings. */
  restartOnboarding: () => Promise<void>;
}

const ProfileContext = createContext<Ctx | undefined>(undefined);

export function ProfileProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [profile, setProfile] = useState<Profile>(DEFAULT_PROFILE);

  useEffect(() => {
    (async () => {
      try {
        const [rawProfile, rawAuth] = await Promise.all([
          AsyncStorage.getItem(KEY),
          AsyncStorage.getItem(AUTH_KEY),
        ]);
        if (rawProfile) setProfile({ ...DEFAULT_PROFILE, ...JSON.parse(rawProfile) });
        if (rawAuth) setSignedIn(JSON.parse(rawAuth)?.signedIn === true);
      } catch {
        // Corrupt storage should never block the app from opening.
      } finally {
        setReady(true);
      }
    })();
  }, []);

  const persist = useCallback(async (next: Profile) => {
    setProfile(next);
    await AsyncStorage.setItem(KEY, JSON.stringify(next));
  }, []);

  const patch = useCallback(
    async (p: Partial<Profile>) => {
      setProfile((cur) => {
        const next = { ...cur, ...p };
        AsyncStorage.setItem(KEY, JSON.stringify(next)).catch(() => {});
        return next;
      });
    },
    [],
  );

  const value = useMemo<Ctx>(
    () => ({
      ready,
      signedIn,
      profile,
      onboarded: Boolean(profile.onboardedAt) && profile.impairments.length > 0,
      signIn: async (displayName: string) => {
        setSignedIn(true);
        await AsyncStorage.setItem(AUTH_KEY, JSON.stringify({ signedIn: true }));
        await patch({ displayName });
      },
      signOut: async () => {
        setSignedIn(false);
        await AsyncStorage.multiRemove([KEY, AUTH_KEY]);
        setProfile(DEFAULT_PROFILE);
      },
      patch,
      completeOnboarding: async (p: Partial<Profile>) => {
        await patch({ ...p, onboardedAt: new Date().toISOString() });
      },
      restartOnboarding: async () => {
        // Keep preferences, drop the completion stamp so the root navigator
        // re-mounts the onboarding stack.
        await patch({ onboardedAt: undefined });
      },
    }),
    [ready, signedIn, profile, patch, persist],
  );

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile() {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error('useProfile must be used inside <ProfileProvider>');
  return ctx;
}
