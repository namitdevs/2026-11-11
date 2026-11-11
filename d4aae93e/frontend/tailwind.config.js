/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#060a12",
        panel: "#0c1322",
        line: "#1b2740",
        mint: "#35f0b0",
        sky: "#59c2ff",
        amber: "#ffb545",
        rose: "#ff6b81",
      },
      boxShadow: {
        glow: "0 0 40px -12px rgba(53,240,176,0.35)",
      },
    },
  },
  plugins: [],
};
