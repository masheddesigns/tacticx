/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#ecfdf5',
          100: '#d1fae5',
          400: '#34d399',
          500: '#21e786', // FotMob Signature Green
          600: '#10b981',
          700: '#059669',
        },
        surface: {
          base: '#0e1015',        // FotMob true dark canvas
          card: '#161922',        // FotMob primary card surface
          cardMuted: '#1e222e',   // FotMob elevated / nested card
          border: '#242938',      // FotMob subtle separator
          borderLight: '#32394d', // FotMob hover highlight border
        },
        fotmob: {
          bg: '#0e1015',
          card: '#161922',
          cardLight: '#1e222e',
          green: '#21e786',
          greenHover: '#1cd378',
          red: '#ff4b4b',
          amber: '#f59e0b',
          blue: '#3b82f6',
          border: '#242938',
          textMuted: '#94a3b8',
        }
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"Roboto Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      }
    },
  },
  plugins: [],
}

