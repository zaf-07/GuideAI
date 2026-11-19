/** Domain types for the accessibility profile that reshapes the whole app. */

export type ImpairmentId = 'vision' | 'hearing' | 'deafblind';

export type VisionLevel = 'low_vision' | 'legally_blind' | 'totally_blind';
export type HearingLevel = 'hard_of_hearing' | 'deaf' | 'profoundly_deaf';
export type SignLanguage = 'ASL' | 'BSL' | 'ISL' | 'LSF' | 'other';
export type Guidance = 'concise' | 'detailed';

export interface Profile {
  /** Primary impairments. `deafblind` implies both tracks are active. */
  impairments: ImpairmentId[];
  visionLevel?: VisionLevel;
  hearingLevel?: HearingLevel;
  signLanguage?: SignLanguage;
  /** How verbose spoken/haptic scene descriptions should be. */
  guidance: Guidance;
  /** Speech rate multiplier for scene narration. */
  speechRate: number;
  /** Continuous haptic proximity feedback while navigating. */
  haptics: boolean;
  /** Large, high-contrast captions for every spoken line. */
  captions: boolean;
  /** Keep the memory graph on-device only. */
  localOnlyMemory: boolean;
  displayName?: string;
  onboardedAt?: string;
}

export const DEFAULT_PROFILE: Profile = {
  impairments: [],
  guidance: 'detailed',
  speechRate: 1,
  haptics: true,
  captions: true,
  localOnlyMemory: true,
};

export const hasVisionTrack = (p: Profile) =>
  p.impairments.includes('vision') || p.impairments.includes('deafblind');

export const hasHearingTrack = (p: Profile) =>
  p.impairments.includes('hearing') || p.impairments.includes('deafblind');

export const isDeafBlind = (p: Profile) => p.impairments.includes('deafblind');

/** Blind users get audio-first affordances; deaf users get visual-first ones. */
export const prefersAudioFirst = (p: Profile) =>
  hasVisionTrack(p) && !p.impairments.includes('deafblind');

export const IMPAIRMENT_LABEL: Record<ImpairmentId, string> = {
  vision: 'Blind or low vision',
  hearing: 'Deaf or hard of hearing',
  deafblind: 'Deaf-blind',
};
