import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    hmr: {
      clientPort: 5173,
    },
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL ?? "http://api:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
