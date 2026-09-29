import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      colors: {
        ss: {
          bg: '#0b0f14',
          panel: '#111821',
          border: '#1c2431',
          text: '#e2e8f0',
          textmuted: '#94a3b8',
          accent: '#22d3ee',
        },
      },
      keyframes: {
        flash: { '0%, 100%': { backgroundColor: 'transparent' }, '15%, 60%': { backgroundColor: 'rgba(34, 211, 238, 0.14)' } },
        'slide-in': { from: { transform: 'translateX(24px)', opacity: '0' }, to: { transform: 'translateX(0)', opacity: '1' } },
        pop: { from: { transform: 'scale(0.9)', opacity: '0' }, to: { transform: 'scale(1)', opacity: '1' } },
      },
      animation: {
        flash: 'flash 2.2s ease-in-out 3',
        'slide-in': 'slide-in 180ms ease-out',
        pop: 'pop 320ms cubic-bezier(.2,.9,.3,1.2)',
      },
    },
  },
  plugins: [],
} satisfies Config;
