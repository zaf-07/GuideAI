// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  { ignores: ['**/dist/**', '**/scripts/**', '**/tests/**'] },
  expoConfig,
  {
    rules: {
      // Existing GuideLens engines intentionally keep the latest values in
      // refs for animation and streaming callbacks. React Compiler is not
      // enabled for this app, so its compiler-only lint rules do not apply.
      'react-hooks/refs': 'off',
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/preserve-manual-memoization': 'off',
      'react-hooks/immutability': 'off',
      'react/no-unescaped-entities': 'off',
    },
  },
]);
