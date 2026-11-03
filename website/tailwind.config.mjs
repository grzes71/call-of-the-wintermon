/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {
      colors: {
        atari: {
          bg: '#06080e',
          surface: '#0a0f1d',
          surfaceLight: '#121a30',
          border: '#1b2a47',
          green: '#00ff66',
          greenDim: '#00aa44',
          amber: '#ffb000',
          amberDim: '#cc8c00',
          cyan: '#00e5ff',
          cyanDim: '#009bb3',
          red: '#ff4444',
          text: '#e2e8f0',
          muted: '#94a3b8',
          dark: '#030508',
        },
      },
      fontFamily: {
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Consolas',
          '"Liberation Mono"',
          '"Courier New"',
          'monospace',
        ],
      },
      boxShadow: {
        'atari-green': '0 0 15px rgba(0, 255, 102, 0.25)',
        'atari-amber': '0 0 15px rgba(255, 176, 0, 0.25)',
        'atari-cyan': '0 0 15px rgba(0, 229, 255, 0.25)',
      },
    },
  },
  plugins: [],
};

