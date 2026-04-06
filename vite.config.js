import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 代理所有 /api 请求（包括 WebSocket）
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true, // ✅ 启用 WebSocket 代理
      },
    },
  },
});
