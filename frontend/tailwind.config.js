/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1C2024",
        teal: "#1E5631",
        agri: "#1E5631",
        gold: "#C68B59",
        mist: "#FAF8F5",
        cream: "#FAF8F5",
        slate: "#5B6472",
        rain: "#3A7CA5",
      },
      fontFamily: {
        serif: ["Fraunces", "Georgia", "serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
}
