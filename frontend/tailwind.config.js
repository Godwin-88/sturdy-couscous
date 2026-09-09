/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Raleway", "system-ui", "sans-serif"],
        mono: ["Raleway", "system-ui", "sans-serif"],
      },
      colors: {
        brand: {
          50:  "#f0f6ff",
          100: "#c8e1ff",
          200: "#9ac7ff",
          300: "#79c0ff",
          400: "#58a6ff",
          500: "#1f6feb",
          600: "#0969da",
          700: "#0550ae",
          800: "#033d8b",
          900: "#02274f",
          950: "#011b38",
        },
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
      },
    },
  },
  plugins: [],
};
