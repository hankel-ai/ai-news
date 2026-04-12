import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        hankel: {
          bg: "#0f172a",
          surface: "#1e293b",
          text: "#e2e8f0",
          muted: "#94a3b8",
          accent: "#60a5fa",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
