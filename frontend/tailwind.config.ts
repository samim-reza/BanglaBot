import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        surface: "hsl(var(--surface))",
        primary: "hsl(var(--primary))",
        "primary-dark": "hsl(var(--primary-dark))",
        "primary-foreground": "hsl(var(--primary-foreground))",
        secondary: "hsl(var(--secondary))",
        "secondary-foreground": "hsl(var(--secondary-foreground))",
        muted: "hsl(var(--muted))",
        "muted-foreground": "hsl(var(--muted-foreground))",
        accent: "hsl(var(--accent))",
        "accent-foreground": "hsl(var(--accent-foreground))",
        tint: "hsl(var(--tint))",
        "tint-strong": "hsl(var(--tint-strong))",
        destructive: "hsl(var(--destructive))",
        "destructive-foreground": "hsl(var(--destructive-foreground))",
        card: "hsl(var(--card))",
        "card-foreground": "hsl(var(--card-foreground))",
        brand: {
          teal: "#0d9488",
          dark: "#0f766e",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "8px",
        sm: "6px",
      },
      fontFamily: {
        sans: ["var(--font-noto-bengali)", "Noto Sans Bengali", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
