const baseUrl = process.env.EXPO_PUBLIC_BASE_URL || '/';

module.exports = {
  expo: {
    name: 'GuideAI',
    slug: 'guideai',
    version: '1.0.0',
    orientation: 'portrait',
    scheme: 'guideai',
    userInterfaceStyle: 'dark',
    backgroundColor: '#07110F',
    icon: './assets/icon.png',
    splash: {
      image: './assets/splash-icon.png',
      resizeMode: 'contain',
      backgroundColor: '#07110F',
    },
    ios: {
      supportsTablet: true,
      bundleIdentifier: 'com.guideai.app',
      infoPlist: {
        NSCameraUsageDescription:
          'GuideAI uses the camera to describe your surroundings, measure distance to obstacles, and read sign language. Video is processed on this device and never stored.',
        NSMicrophoneUsageDescription:
          "GuideAI listens so another person's speech can be captioned and translated into sign language.",
        NSSpeechRecognitionUsageDescription:
          'GuideAI transcribes speech so it can be shown as captions and signed back to you.',
        NSLocationWhenInUseUsageDescription:
          'GuideAI uses your location and heading to guide you along pavements, crossings and traffic.',
        NSMotionUsageDescription:
          'GuideAI uses motion sensors to know which way you are facing while navigating.',
        UIBackgroundModes: ['audio'],
      },
    },
    android: {
      package: 'com.guideai.app',
      versionCode: 1,
      adaptiveIcon: {
        backgroundColor: '#07110F',
        foregroundImage: './assets/android-icon-foreground.png',
        backgroundImage: './assets/android-icon-background.png',
        monochromeImage: './assets/android-icon-monochrome.png',
      },
      permissions: ['CAMERA', 'RECORD_AUDIO'],
    },
    web: {
      bundler: 'metro',
      output: 'single',
      name: 'GuideAI — accessible AI vision and sign language',
      favicon: './assets/favicon.png',
    },
    plugins: [
      'expo-router',
      'expo-asset',
      'onnxruntime-react-native',
      ['expo-camera', { cameraPermission: 'Allow GuideAI to identify nearby objects and obstacles.' }],
      [
        'expo-speech-recognition',
        {
          microphonePermission: 'Allow GuideAI to use the microphone for Bridge replies.',
          speechRecognitionPermission: 'Allow GuideAI to turn spoken Bridge replies into text.',
        },
      ],
    ],
    experiments: {
      typedRoutes: true,
      baseUrl,
    },
  },
};
