import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL("index.html", import.meta.url)),
        brand: fileURLToPath(new URL("brand.html", import.meta.url)),
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5176,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/data/photos": "http://127.0.0.1:8000",
    },
  },
  preview: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/data/photos": "http://127.0.0.1:8000",
    },
  },
});
