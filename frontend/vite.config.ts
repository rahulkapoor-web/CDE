import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 3000,
    // Allow Gitpod/Ona preview hostnames (and any host) to reach the dev server.
    allowedHosts: true,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // Plan generation/refine can take a couple of minutes (LLM latency).
        // Without this, the proxy's ~120s default aborts the request and the
        // UI shows a failure even though the backend finishes and saves the
        // plan. Allow up to 10 minutes.
        timeout: 600000,
        proxyTimeout: 600000,
      },
    },
  },
});
