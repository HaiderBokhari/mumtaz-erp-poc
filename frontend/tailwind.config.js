/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f2f6fc',
          100: '#e1ebf8',
          500: '#1d4ed8',
          600: '#1a3fb5',
          700: '#16358f',
          900: '#0f2158',
        },
      },
    },
  },
  plugins: [],
}
