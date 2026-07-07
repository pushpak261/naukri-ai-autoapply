/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--color-bg)',
        surface: 'var(--color-surface)',
        'surface-hover': 'var(--color-surface-hover)',
        'surface-elevated': 'var(--color-surface-elevated)',
        border: 'var(--color-border)',
        'border-subtle': 'var(--color-border-subtle)',
        text: 'var(--color-text)',
        secondary: 'var(--color-text-secondary)',
        muted: 'var(--color-text-muted)',
        primary: 'var(--color-primary)',
        'primary-hover': 'var(--color-primary-hover)',
        'on-primary': 'var(--color-on-primary)',
        success: 'var(--color-success)',
        warning: 'var(--color-warning)',
        danger: 'var(--color-danger)',
        input: 'var(--color-input-bg)',
        // shadcn-compatible
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: 'hsl(var(--card))',
        'card-foreground': 'hsl(var(--card-foreground))',
        'primary-foreground': 'hsl(var(--primary-foreground))',
        'muted-foreground': 'hsl(var(--muted-foreground))',
        accent: 'hsl(var(--accent))',
        'accent-foreground': 'hsl(var(--accent-foreground))',
        destructive: 'hsl(var(--destructive))',
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
    },
  },
  plugins: [],
}
