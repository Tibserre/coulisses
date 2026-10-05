import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Everything is local (P1): the dev server and the service both listen on 127.0.0.1.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
});
