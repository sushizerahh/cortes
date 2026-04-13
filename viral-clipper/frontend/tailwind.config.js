/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        neon: '#00FF88',
        'neon-dim': '#00cc6a',
        bg: '#0a0a0f',
        surface: '#12121a',
        card: '#1a1a26',
        border: '#2a2a3a',
        muted: '#6b7280',
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Space Mono"', 'monospace'],
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        neon: '0 0 20px rgba(0,255,136,0.3)',
        'neon-sm': '0 0 8px rgba(0,255,136,0.2)',
      },
    },
  },
  plugins: [],
}
