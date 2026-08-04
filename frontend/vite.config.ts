import path from "node:path";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    tanstackRouter({ target: "react", autoCodeSplitting: true }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    // Overridable so a second instance can run alongside the default stack:
    // FRONTEND_PORT picks the dev-server port, API_TARGET points the proxy at
    // whichever backend that instance is talking to.
    port: Number(process.env.FRONTEND_PORT) || 5173,
    proxy: {
      "/api": {
        target: process.env.API_TARGET ?? "http://localhost:8000",
        changeOrigin: false,
      },
    },
  },
});
