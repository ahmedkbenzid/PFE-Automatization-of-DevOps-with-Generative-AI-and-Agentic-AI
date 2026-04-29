/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{html,ts}",
    "./src/app/components/**/*.{html,ts}"
  ],
  theme: {
    extend: {
      colors: {
        'devflow-bg': '#0a0b0d',
        'devflow-surface': '#111318',
        'devflow-elevated': '#1a1d24',
        'devflow-border': '#2a2f3a',
        'devflow-text': '#f0f2f5',
        'devflow-text-secondary': '#8b92a5',
        'devflow-text-muted': '#4a5168',
        'devflow-accent': '#3b82f6',
        'devflow-success': '#22c55e',
        'devflow-error': '#ef4444',
        'devflow-warning': '#f59e0b',
        'devflow-running': '#a78bfa',
      },
      fontFamily: {
        'sans': ['Inter', 'Helvetica Neue', 'sans-serif'],
        'mono': ['JetBrains Mono', 'Fira Code', 'Cascadia Code', 'monospace'],
      },
      animation: {
        'pulse-dot': 'pulse-dot 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        'pulse-dot': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.3' },
        }
      }
    },
  },
  plugins: [],
}
