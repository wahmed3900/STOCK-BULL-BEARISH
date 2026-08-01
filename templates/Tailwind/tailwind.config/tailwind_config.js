/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        premium: {
          glass: "rgba(30, 41, 59, 0.6)",
          neon: "#10b981",
          indigo: "#6366f1",
        },
      },
      boxShadow: {
        premium: "0 8px 25px rgba(0, 0, 0, 0.4)",
      },
      backdropBlur: {
        xs: "2px",
        sm: "4px",
        md: "12px",
      },
      fontFamily: {
        inter: ["Inter", "sans-serif"],
      },
    },
  },
  plugins: [],
};
