import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-noto)", "var(--font-inter)", "ui-sans-serif", "sans-serif"],
        mono: ["var(--font-inter)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
