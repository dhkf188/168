import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 代理 API 请求到后端
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      // 代理远程屏幕 WebSocket
      "/api/remote/ws": {
        target: "ws://localhost:8000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
