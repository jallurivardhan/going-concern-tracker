import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class", // never applied — dark mode is intentionally disabled
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        severity: {
          critical: "#dc2626", // red-600
          elevated: "#d97706", // amber-600
          watch: "#475569",    // slate-600
          resolved: "#059669", // emerald-600
        },
      },
      fontFamily: {
        serif: ["ui-serif", "Georgia", '"Times New Roman"', "serif"],
        sans: ["ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
