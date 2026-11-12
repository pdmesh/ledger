import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// In development the UI talks to the local backend on 127.0.0.1:8765 through Vite's proxy.
// Inside Tauri, the backend URL and per-launch token come from the shell (see src/lib/api.ts).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  build: { target: "es2022", outDir: "dist", chunkSizeWarningLimit: 1500 },
});
