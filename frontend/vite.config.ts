import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1", port: 5174, strictPort: true,
    proxy: {
      "/runs": "http://127.0.0.1:8001", "/history": "http://127.0.0.1:8001",
      "/evaluation": "http://127.0.0.1:8001", "/assistant": "http://127.0.0.1:8001",
      "/evidence": "http://127.0.0.1:8001", "/health": "http://127.0.0.1:8001",
      "/ready": "http://127.0.0.1:8001", "/auth": "http://127.0.0.1:8001",
      "/tests": "http://127.0.0.1:8001", "/suites": "http://127.0.0.1:8001",
      "/model-profiles": "http://127.0.0.1:8001", "/previews": "http://127.0.0.1:8001",
      "/executions": "http://127.0.0.1:8001",
    },
  },
});
