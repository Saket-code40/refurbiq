import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" keeps the build portable across Vercel / Netlify / GitHub Pages.
export default defineConfig({
  plugins: [react()],
  base: "./",
});