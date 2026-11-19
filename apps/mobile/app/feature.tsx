import { useLocalSearchParams } from 'expo-router';
import { FeatureScreen } from '../src/screens/FeatureScreen';

export default function Feature() {
  const { key, title } = useLocalSearchParams<{ key: string; title: string }>();
  return <FeatureScreen featureKey={key ?? 'scene'} title={title ?? 'Feature'} />;
}
