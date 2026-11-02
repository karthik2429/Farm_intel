import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./app/**/*.{ts,tsx}",
    "./src/**/*.{ts,tsx}",
    "./index.html",
  ],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: { DEFAULT: "1rem", md: "1.5rem", xl: "2rem" },
      screens: { "2xl": "1280px" },
    },
    extend: {
      fontFamily: {
        display: ['"Plus Jakarta Sans"', '"Noto Sans"', "system-ui", "sans-serif"],
        sans: ['"Noto Sans"', '"Plus Jakarta Sans"', "system-ui", "-apple-system", "sans-serif"],
        devanagari: ['"Noto Sans Devanagari"', '"Noto Sans"', "sans-serif"],
        kannada: ['"Noto Sans Kannada"', '"Noto Sans"', "sans-serif"],
        telugu: ['"Noto Sans Telugu"', '"Noto Sans"', "sans-serif"],
        tamil: ['"Noto Sans Tamil"', '"Noto Sans"', "sans-serif"],
        malayalam: ['"Noto Sans Malayalam"', '"Noto Sans"', "sans-serif"],
        gujarati: ['"Noto Sans Gujarati"', '"Noto Sans"', "sans-serif"],
        bengali: ['"Noto Sans Bengali"', '"Noto Sans"', "sans-serif"],
        gurmukhi: ['"Noto Sans Gurmukhi"', '"Noto Sans"', "sans-serif"],
        oriya: ['"Noto Sans Oriya"', '"Noto Sans"', "sans-serif"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        surface: {
          DEFAULT: "hsl(var(--surface))",
          2: "hsl(var(--surface-2))",
        },
        forest: "hsl(var(--forest))",
        leaf: "hsl(var(--leaf))",
        harvest: "hsl(var(--accent))",
        ink: {
          DEFAULT: "hsl(var(--text))",
          muted: "hsl(var(--text-muted))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
          600: "hsl(var(--primary-600))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        sidebar: {
          DEFAULT: "hsl(var(--sidebar-background))",
          foreground: "hsl(var(--sidebar-foreground))",
          primary: "hsl(var(--sidebar-primary))",
          "primary-foreground": "hsl(var(--sidebar-primary-foreground))",
          accent: "hsl(var(--sidebar-accent))",
          "accent-foreground": "hsl(var(--sidebar-accent-foreground))",
          border: "hsl(var(--sidebar-border))",
          ring: "hsl(var(--sidebar-ring))",
        },
      },
      fontWeight: {
        400: "400",
        500: "500",
        600: "600",
        700: "700",
        800: "800",
      },
      borderRadius: {
        sm: "var(--r-sm)",
        md: "var(--r-md)",
        lg: "var(--r-lg)",
        xl: "calc(var(--r-lg) + 6px)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        glow: "var(--shadow-glow)",
      },
      backgroundImage: {
        hero: "var(--grad-hero)",
        gold: "var(--grad-gold)",
        leaf: "var(--grad-leaf)",
        surface: "var(--grad-surface)",
      },
      spacing: {
        18: "4.5rem",
        22: "5.5rem",
        34: "8.5rem",
      },
      maxWidth: {
        content: "1200px",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        shimmer: {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.96)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        "pulse-soft": {
          "0%, 100%": { boxShadow: "0 0 0 0 hsl(var(--primary) / 0.45)" },
          "50%": { boxShadow: "0 0 0 12px hsl(var(--primary) / 0)" },
        },
        "slide-up-sheet": {
          "0%": { transform: "translateY(24px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        shimmer: "shimmer 1.4s ease-in-out infinite",
        "fade-up": "fade-up 260ms cubic-bezier(0.22,1,0.36,1) both",
        "fade-in": "fade-in 200ms ease-out both",
        "scale-in": "scale-in 220ms cubic-bezier(0.22,1,0.36,1) both",
        "pulse-soft": "pulse-soft 2.4s ease-in-out infinite",
        "slide-up-sheet": "slide-up-sheet 260ms cubic-bezier(0.22,1,0.36,1) both",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config;
