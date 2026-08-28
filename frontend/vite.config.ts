import { defineConfig } from "vite";

export default defineConfig({
  server: { host: "0.0.0.0", port: 5173 },
  preview: {
    host: "0.0.0.0",
    port: 5173,
    // Railway (and other PaaS) public hostnames are not localhost — allow them in preview mode.
    allowedHosts: true,
  },
  esbuild: { jsx: "automatic" },
});
