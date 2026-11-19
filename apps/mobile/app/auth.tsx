import { Redirect } from 'expo-router';
import { AuthScreen } from '../src/screens/AuthScreen';
import { useProfile } from '../src/state/ProfileContext';

export default function Auth() {
  const { ready, signedIn } = useProfile();
  if (ready && signedIn) return <Redirect href="/" />;
  return <AuthScreen />;
}
