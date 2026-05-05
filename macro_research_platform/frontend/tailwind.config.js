/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        /* Bloomberg Terminal Design System — Institutional */
        bg: '#06090c',
        'surface-1': '#0d1117',
        'surface-2': '#131920',
        'surface-3': '#1a2230',
        'surface-4': '#1e2736',
        border: '#1e2d3d',
        'border-subtle': '#151f2e',
        'border-strong': '#2a3f55',

        /* Text hierarchy */
        'text-primary': '#e8edf2',
        'text-secondary': '#8895a4',
        'text-tertiary': '#4a5568',
        'text-inverse': '#090c0f',

        /* Bloomberg orange — primary terminal accent */
        bloomberg: '#f07030',
        'bloomberg-dim': 'rgba(240, 112, 48, 0.15)',
        'bloomberg-muted': 'rgba(240, 112, 48, 0.08)',
        'bloomberg-border': 'rgba(240, 112, 48, 0.30)',

        /* Teal — secondary action color */
        accent: '#00d4aa',
        'accent-dim': '#00a882',
        'accent-muted': 'rgba(0, 212, 170, 0.10)',
        'accent-border': 'rgba(0, 212, 170, 0.25)',

        /* Semantic colors (data only) */
        green: '#22c55e',
        'green-dim': 'rgba(34, 197, 94, 0.12)',
        red: '#ef4444',
        'red-dim': 'rgba(239, 68, 68, 0.12)',
        amber: '#f59e0b',
        'amber-dim': 'rgba(245, 158, 11, 0.12)',
        blue: '#3b82f6',
        'blue-dim': 'rgba(59, 130, 246, 0.12)',
        purple: '#a855f7',
        'purple-dim': 'rgba(168, 85, 247, 0.12)',

        /* Legacy aliases for compatibility */
        terminal: {
          bg: '#090c0f',
          card: '#0d1117',
          elevated: '#131920',
          border: '#1e2d3d',
          'border-light': '#151f2e',
          amber: '#00d4aa',
          green: '#22c55e',
          red: '#ef4444',
          blue: '#3b82f6',
        },

        /* Text legacy */
        text: {
          primary: '#e8edf2',
          secondary: '#8895a4',
          muted: '#4a5568',
        },

        /* Accent legacy */
        accent: {
          amber: '#00d4aa',
          'amber-dark': '#00a882',
          green: '#22c55e',
          'green-light': '#4ade80',
          red: '#ef4444',
          'red-light': '#f87171',
          blue: '#3b82f6',
          cyan: '#22d3ee',
          purple: '#a855f7',
        },

        /* Regime colors */
        regime: {
          'risk-on': '#22c55e',
          'late-cycle': '#f59e0b',
          'risk-off': '#ef4444',
          recovery: '#3b82f6',
        },
      },

      fontFamily: {
        mono: ['Geist Mono', 'JetBrains Mono', 'Fira Code', 'Consolas', 'Monaco', 'monospace'],
        sans: ['Geist', 'Inter', 'system-ui', 'sans-serif'],
      },

      fontSize: {
        '2xs': ['10px', { lineHeight: '1.4' }],
        'xs': ['11px', { lineHeight: '1.4' }],
        'sm': ['12px', { lineHeight: '1.5' }],
        'base': ['13px', { lineHeight: '1.5' }],
        'md': ['14px', { lineHeight: '1.5' }],
        'lg': ['16px', { lineHeight: '1.4' }],
        'xl': ['20px', { lineHeight: '1.3' }],
      },

      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
        '26': '6.5rem',
        '30': '7.5rem',
      },

      borderRadius: {
        'sm': '2px',
        'md': '4px',
        'lg': '6px',
      },

      animation: {
        'pulse-live': 'pulse-live 4s ease-in-out infinite',
        'fill-bar': 'fill-bar 600ms cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'flash': 'flash 1s ease-in-out',
        'shimmer': 'shimmer 1.5s infinite',
      },

      keyframes: {
        'pulse-live': {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.5', transform: 'scale(0.85)' },
        },
        'fill-bar': {
          from: { width: '0' },
        },
        'flash': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5', backgroundColor: 'rgba(0, 212, 170, 0.1)' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },

      transitionTimingFunction: {
        'data': 'cubic-bezier(0.16, 1, 0.3, 1)',
      },

      transitionDuration: {
        '400': '400ms',
      },

      boxShadow: {
        'sm': '0 1px 3px rgba(0,0,0,0.4)',
        'md': '0 4px 12px rgba(0,0,0,0.5)',
      },

      /* Layout dimensions */
      height: {
        'topbar': '64px',
      },
      width: {
        'sidebar': '220px',
        'sidebar-collapsed': '48px',
        'detail': '280px',
      },
    },
  },
  plugins: [],
}
