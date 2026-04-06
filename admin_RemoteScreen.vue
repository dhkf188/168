<!-- admin_RemoteScreen.vue - 专业级远程屏幕查看页面（完美契合后端）-->
<template>
  <div class="remote-screen">
    <!-- 左侧员工列表抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      title="在线员工"
      size="320px"
      :with-header="true"
      direction="ltr"
    >
      <div class="employee-list" v-loading="loadingEmployees">
        <!-- 搜索框 -->
        <el-input
          v-model="searchKeyword"
          placeholder="搜索员工姓名/计算机"
          :prefix-icon="Search"
          clearable
          size="small"
          class="search-input"
        />

        <el-empty
          v-if="filteredClients.length === 0"
          description="暂无在线员工"
        />

        <div
          v-for="client in filteredClients"
          :key="client.client_id"
          class="employee-item"
          :class="{
            active: currentEmployeeId === client.employee_id,
            viewing: client.is_viewing,
          }"
          @click="selectEmployee(client)"
        >
          <div class="employee-status">
            <el-badge
              :value="client.viewer_count"
              :hidden="!client.is_viewing"
              class="viewer-badge"
            >
              <span
                class="status-dot"
                :class="{ online: true, viewing: client.is_viewing }"
              ></span>
            </el-badge>
          </div>
          <div class="employee-info">
            <div class="employee-name">
              {{ client.employee_name }}
              <el-tag
                v-if="client.is_viewing"
                size="small"
                type="warning"
                effect="light"
                round
              >
                {{ client.viewer_count }}人查看
              </el-tag>
            </div>
            <div class="employee-detail">
              <span>{{ client.computer_name }}</span>
              <span class="ip">{{ client.ip_address }}</span>
            </div>
            <div class="employee-capabilities">
              <el-tooltip
                v-if="client.capabilities.diff_frame"
                content="差异帧传输"
                placement="top"
              >
                <el-icon size="14" color="#67C23A"><Connection /></el-icon>
              </el-tooltip>
              <el-tooltip
                v-if="client.capabilities.region_detect"
                content="区域检测"
                placement="top"
              >
                <el-icon size="14" color="#409EFF"><Grid /></el-icon>
              </el-tooltip>
              <el-tooltip
                v-if="client.capabilities.h264"
                content="H.264加速"
                placement="top"
              >
                <el-icon size="14" color="#E6A23C"><VideoCamera /></el-icon>
              </el-tooltip>
              <el-tooltip
                v-if="client.capabilities.qr_detect"
                content="二维码检测"
                placement="top"
              >
                <el-icon size="14" color="#F56C6C"><Camera /></el-icon>
              </el-tooltip>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="drawer-footer">
          <el-button
            @click="refreshOnlineClients"
            :loading="refreshing"
            size="small"
          >
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
          <span class="online-count">在线: {{ onlineClients.length }}</span>
        </div>
      </template>
    </el-drawer>

    <!-- 主区域 -->
    <div class="main-area">
      <!-- 顶部工具栏 -->
      <div class="toolbar">
        <el-button-group>
          <el-button @click="drawerVisible = true">
            <el-icon><Grid /></el-icon>员工列表
          </el-button>

          <el-button
            v-if="currentEmployeeId"
            :type="isViewing ? 'danger' : 'primary'"
            @click="toggleView"
            :loading="connecting"
          >
            <el-icon :class="{ 'is-loading': connecting }">
              <VideoCamera v-if="!isViewing" />
              <VideoPause v-else />
            </el-icon>
            {{ isViewing ? "停止查看" : "开始查看" }}
          </el-button>
        </el-button-group>

        <el-button-group v-if="isViewing" class="action-buttons">
          <el-button @click="takeScreenshot">
            <el-icon><Camera /></el-icon>截图
          </el-button>

          <el-button @click="fullscreen" :disabled="!screenImage">
            <el-icon><FullScreen /></el-icon>全屏
          </el-button>

          <el-button @click="resetView" :disabled="!screenImage">
            <el-icon><Refresh /></el-icon>重置视图
          </el-button>
        </el-button-group>

        <div class="status-info" v-if="isViewing">
          <el-tag
            size="small"
            :type="networkQuality.type"
            effect="dark"
            class="status-tag"
          >
            <el-icon><Connection /></el-icon>
            {{ networkQuality.text }} ({{ stats.fpsActual || currentFps }}fps /
            {{ currentQuality }}%)
          </el-tag>

          <el-tag size="small" type="info" effect="plain" class="status-tag">
            <el-icon><Timer /></el-icon>
            {{ stats.avgLatency.toFixed(0) }}ms
          </el-tag>

          <el-tag size="small" type="success" effect="plain" class="status-tag">
            <el-icon><DataLine /></el-icon>
            {{ formatBytes(stats.bytesReceived) }}
          </el-tag>
        </div>
      </div>

      <!-- 高级控制面板（可折叠）-->
      <el-collapse v-if="isViewing" class="advanced-controls">
        <el-collapse-item title="高级设置" name="advanced">
          <div class="control-panel">
            <div class="control-row">
              <span class="control-label">画质</span>
              <el-slider
                v-model="currentQuality"
                :min="30"
                :max="95"
                :step="5"
                show-input
                input-size="small"
                @change="changeQuality"
                class="control-slider"
              />
            </div>

            <div class="control-row">
              <span class="control-label">帧率</span>
              <el-slider
                v-model="currentFps"
                :min="1"
                :max="10"
                :step="1"
                show-input
                input-size="small"
                @change="changeFps"
                class="control-slider"
              />
            </div>

            <div class="control-row">
              <span class="control-label">优化选项</span>
              <div class="control-switches">
                <el-switch
                  v-model="enableDiff"
                  active-text="差异帧"
                  @change="toggleDiff"
                  size="small"
                />
                <el-switch
                  v-model="enableRegion"
                  active-text="区域检测"
                  @change="toggleRegion"
                  size="small"
                />
                <el-switch
                  v-if="clientCapabilities.qr_detect"
                  v-model="enableQr"
                  active-text="二维码"
                  @change="toggleQr"
                  size="small"
                />
              </div>
            </div>

            <div class="control-row">
              <span class="control-label">统计</span>
              <div class="stats-text">
                <span>压缩比: {{ stats.compressionRatio.toFixed(1) }}%</span>
                <span>差异率: {{ stats.diffRatio.toFixed(1) }}%</span>
                <span>区域率: {{ stats.regionRatio.toFixed(1) }}%</span>
              </div>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>

      <!-- 屏幕显示区域 -->
      <div
        class="screen-container"
        ref="screenContainer"
        @wheel="handleZoom"
        @mousedown="startPan"
        @mousemove="pan"
        @mouseup="stopPan"
        @mouseleave="stopPan"
      >
        <div
          class="screen-wrapper"
          :style="{
            transform: `scale(${zoom}) translate(${panX}px, ${panY}px)`,
            transformOrigin: '0 0',
          }"
          ref="screenWrapper"
        >
          <img
            v-if="screenImage"
            :src="screenImage"
            class="screen-image"
            :style="{ width: screenWidth + 'px', height: screenHeight + 'px' }"
            @load="imageLoaded"
            @error="imageError"
            ref="screenImageRef"
          />

          <!-- 二维码标记 -->
          <div
            v-for="(qr, index) in qrCodes"
            :key="index"
            class="qr-marker"
            :style="{
              left: qr.rect.x * zoom + 'px',
              top: qr.rect.y * zoom + 'px',
              width: qr.rect.width * zoom + 'px',
              height: qr.rect.height * zoom + 'px',
            }"
            :title="qr.data"
          >
            <el-tooltip :content="qr.data" placement="top">
              <div class="qr-content">QR</div>
            </el-tooltip>
          </div>
        </div>

        <div v-if="!screenImage && isViewing" class="screen-placeholder">
          <el-empty description="等待画面..." />
        </div>

        <div v-if="!isViewing && currentEmployeeId" class="screen-placeholder">
          <el-empty description="点击开始查看" />
        </div>

        <div v-if="!currentEmployeeId" class="screen-placeholder">
          <el-empty description="请选择员工" />
        </div>

        <!-- 加载遮罩 -->
        <div v-if="connecting" class="loading-mask">
          <el-icon class="is-loading" size="40"><Loading /></el-icon>
          <span>连接中...</span>
        </div>

        <!-- 二维码信息浮层 -->
        <el-card v-if="qrCodes.length > 0" class="qr-panel" shadow="hover">
          <template #header>
            <span>📱 检测到二维码</span>
          </template>
          <div v-for="(qr, idx) in qrCodes" :key="idx" class="qr-item">
            <div class="qr-data">{{ qr.data }}</div>
            <el-button
              link
              type="primary"
              size="small"
              @click="copyQr(qr.data)"
            >
              复制
            </el-button>
          </div>
        </el-card>
      </div>
    </div>

    <!-- 截图预览对话框 -->
    <el-dialog
      v-model="screenshotVisible"
      title="截图预览"
      width="80%"
      :fullscreen="true"
    >
      <img :src="screenshotImage" style="width: 100%; height: auto" />
      <template #footer>
        <el-button @click="screenshotVisible = false">关闭</el-button>
        <el-button type="primary" @click="downloadScreenshot">
          <el-icon><Download /></el-icon>下载
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Grid,
  VideoCamera,
  VideoPause,
  Camera,
  FullScreen,
  Connection,
  Download,
  Refresh,
  Search,
  Timer,
  DataLine,
  Loading,
} from "@element-plus/icons-vue";
import api from "./admin_api";
import { useUserStore } from "./admin_stores";
import pako from "pako";

const userStore = useUserStore();

// ==================== 状态 ====================
const drawerVisible = ref(false);
const loadingEmployees = ref(false);
const refreshing = ref(false);
const connecting = ref(false);
const isViewing = ref(false);
const currentEmployeeId = ref("");
const currentClientId = ref("");
const currentEmployeeName = ref("");
const searchKeyword = ref("");

// 在线客户端列表
const onlineClients = ref([]);

// 筛选后的客户端
const filteredClients = computed(() => {
  if (!searchKeyword.value) return onlineClients.value;
  const keyword = searchKeyword.value.toLowerCase();
  return onlineClients.value.filter(
    (c) =>
      c.employee_name.toLowerCase().includes(keyword) ||
      c.computer_name.toLowerCase().includes(keyword),
  );
});

// 屏幕显示
const screenImage = ref("");
const screenWidth = ref(800);
const screenHeight = ref(600);
const zoom = ref(1);
const panX = ref(0);
const panY = ref(0);
const isPanning = ref(false);
const startPanX = ref(0);
const startPanY = ref(0);

// 质量控制
const currentQuality = ref(80);
const currentFps = ref(5);
const enableDiff = ref(true);
const enableRegion = ref(true);
const enableQr = ref(false);

// 客户端能力
const clientCapabilities = ref({
  diff_frame: true,
  region_detect: true,
  h264: true,
  qr_detect: false,
  max_fps: 10,
  max_quality: 95,
});

// 网络质量
const networkQuality = computed(() => {
  if (stats.value.avgLatency < 100) {
    return { type: "success", text: "优" };
  } else if (stats.value.avgLatency < 300) {
    return { type: "warning", text: "良" };
  } else {
    return { type: "danger", text: "差" };
  }
});

// 统计
const stats = ref({
  framesReceived: 0,
  bytesReceived: 0,
  avgLatency: 0,
  compressionRatio: 100,
  diffRatio: 0,
  regionRatio: 0,
  fpsActual: 0,
  lastFrameTime: 0,
});

// 二维码
const qrCodes = ref([]);

// 截图
const screenshotVisible = ref(false);
const screenshotImage = ref("");

// WebSocket
let ws = null;
let heartbeatTimer = null;
let statsTimer = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;

let isManualDisconnect = false;

// DOM引用
const screenContainer = ref(null);
const screenWrapper = ref(null);
const screenImageRef = ref(null);

// ==================== 工具函数 ====================
const formatBytes = (bytes) => {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
};

// ==================== API方法 ====================
const refreshOnlineClients = async () => {
  refreshing.value = true;
  loadingEmployees.value = true;

  try {
    // 获取 token
    const token = localStorage.getItem("token");
    if (!token) {
      console.error("没有找到token");
      ElMessage.error("登录已过期，请重新登录");
      window.location.href = "/login";
      return;
    }

    // 使用 fetch 而不是 api 实例，避免拦截器问题
    const response = await fetch("/api/remote/clients/online", {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      credentials: "same-origin", // 携带 cookie
    });

    if (!response.ok) {
      if (response.status === 401) {
        ElMessage.error("登录已过期，请重新登录");
        window.location.href = "/login";
        return;
      }
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    // 检查响应类型
    const contentType = response.headers.get("content-type");
    if (!contentType || !contentType.includes("application/json")) {
      console.error("返回的不是JSON:", contentType);
      const text = await response.text();
      console.error("返回内容:", text.substring(0, 200));
      throw new Error("服务器返回了非JSON数据");
    }

    const data = await response.json();
    console.log("在线客户端响应:", data);

    onlineClients.value = data.items || [];

    // 如果当前选中的员工不在列表中，清空选中状态
    if (
      currentEmployeeId.value &&
      !onlineClients.value.some(
        (c) => c.employee_id === currentEmployeeId.value,
      )
    ) {
      currentEmployeeId.value = "";
      currentClientId.value = "";
      currentEmployeeName.value = "";
    }
  } catch (error) {
    console.error("获取在线客户端失败:", error);
    ElMessage.error("获取在线客户端失败: " + error.message);
  } finally {
    refreshing.value = false;
    loadingEmployees.value = false;
  }
};

const selectEmployee = (client) => {
  // 如果正在查看，先断开
  if (isViewing.value) {
    disconnect();
  }

  isManualDisconnect = false;

  currentEmployeeId.value = client.employee_id;
  currentClientId.value = client.client_id;
  currentEmployeeName.value = client.employee_name;
  clientCapabilities.value = client.capabilities || {};

  drawerVisible.value = false;

  ElMessage.success(`已选择员工: ${client.employee_name}`);
};

const toggleView = async () => {
  if (isViewing.value) {
    disconnect();
  } else {
    await connect();
  }
};

// ==================== WebSocket连接 ====================
const connect = async () => {
  isManualDisconnect = false;

  if (!currentEmployeeId.value) {
    ElMessage.warning("请先选择员工");
    return;
  }

  connecting.value = true;

  try {
    const token = localStorage.getItem("token");
    if (!token) {
      ElMessage.error("未登录");
      connecting.value = false;
      return;
    }

    // ===== 🚨 关键修复：对员工ID进行编码 =====
    const encodedEmployeeId = encodeURIComponent(currentEmployeeId.value);
    console.log("原始员工ID:", currentEmployeeId.value);
    console.log("编码后员工ID:", encodedEmployeeId);

    // ===== 权限检查 =====
    let checkRes = null;
    try {
      const checkResponse = await fetch(
        `/api/remote/employees/${encodedEmployeeId}/can-view`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: "application/json",
          },
        },
      );
      if (checkResponse.ok) {
        checkRes = await checkResponse.json();
        console.log("✅ 权限检查成功 (fetch)");
      }
    } catch (fetchError) {
      console.warn("fetch 失败:", fetchError);
      try {
        checkRes = await api.get(
          `/api/remote/employees/${encodedEmployeeId}/can-view`,
        );
        console.log("✅ 权限检查成功 (api)");
      } catch (apiError) {
        console.error("api 也失败:", apiError);
        throw new Error("权限检查失败");
      }
    }

    if (!checkRes || !checkRes.can_view) {
      ElMessage.warning(checkRes?.reason || "无法查看该员工");
      connecting.value = false;
      return;
    }

    clientCapabilities.value = checkRes.capabilities || {};

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/remote/ws/admin/${encodedEmployeeId}?token=${token}`;

    console.log("WebSocket连接信息:", {
      protocol: protocol,
      host: window.location.host,
      wsUrl: wsUrl,
      encodedEmployeeId: encodedEmployeeId,
      tokenLength: token.length,
    });

    console.log("正在连接WebSocket:", wsUrl);

    // 创建WebSocket连接
    ws = new WebSocket(wsUrl);

    // ✅ 关键优化：设置二进制消息处理类型
    ws.binaryType = "blob"; // 使用 Blob 接收二进制数据

    // 设置连接超时
    const connectionTimeout = setTimeout(() => {
      if (ws && ws.readyState === WebSocket.CONNECTING) {
        console.error("❌ WebSocket连接超时");
        ws.close();
        connecting.value = false;
        ElMessage.error("连接超时，请重试");
      }
    }, 10000); // 10秒超时

    ws.onopen = () => {
      clearTimeout(connectionTimeout);
      console.log("✅ WebSocket连接成功");
      console.log("WebSocket状态:", {
        readyState: ws.readyState,
        protocol: ws.protocol,
        url: ws.url,
        binaryType: ws.binaryType,
      });

      connecting.value = false;
      isViewing.value = true;
      reconnectAttempts = 0;
      ElMessage.success(`正在查看 ${currentEmployeeName.value} 的屏幕`);

      // ✅ 关键修复：发送开始查看指令，告诉服务端开始推流
      sendMessage({
        type: "start_view",
        timestamp: Date.now(),
      });

      // 发送初始配置
      sendCommand({
        command: "quality",
        params: { quality: currentQuality.value },
      });

      sendCommand({
        command: "fps",
        params: { fps: currentFps.value },
      });

      // 发送优化配置
      if (!enableDiff.value) {
        sendCommand({
          command: "diff_enable",
          params: { enable: false },
        });
      }

      if (enableQr.value) {
        sendCommand({
          command: "qr_enable",
          params: { enable: true },
        });
      }

      // 启动心跳和统计
      startHeartbeat();
      startStatsUpdate();
    };

    // ✅ 优化：增强的 onmessage 处理，支持二进制帧
    // 在 ws.onmessage 中添加帧头解析
    ws.onmessage = async (event) => {
      console.log("📨 收到原始消息:", {
        type: typeof event.data,
        isBlob: event.data instanceof Blob,
        isString: typeof event.data === "string",
        size: event.data.size,
      });
      try {
        // 处理二进制数据
        if (event.data instanceof Blob) {
          const blob = event.data;

          if (blob.size > 20) {
            // ✅ 至少需要20字节帧头
            try {
              // 读取20字节帧头
              const headerBytes = await blob.slice(0, 20).arrayBuffer();
              const headerView = new Uint8Array(headerBytes);

              const version = headerView[0];
              const frameType = headerView[1];
              const width = (headerView[2] << 8) | headerView[3];
              const height = (headerView[4] << 8) | headerView[5];
              const reserved = (headerView[6] << 8) | headerView[7];
              const frameId =
                (headerView[8] << 24) |
                (headerView[9] << 16) |
                (headerView[10] << 8) |
                headerView[11];
              const timestampMs =
                (headerView[12] << 24) |
                (headerView[13] << 16) |
                (headerView[14] << 8) |
                headerView[15];
              const payloadLen =
                (headerView[16] << 24) |
                (headerView[17] << 16) |
                (headerView[18] << 8) |
                headerView[19];

              console.log("📋 帧头解析:", {
                version,
                frameType,
                width,
                height,
                frameId,
                timestampMs,
                payloadLen,
              });

              // ✅ 验证 payload 长度
              if (blob.size < 20 + payloadLen) {
                console.warn("数据不完整，等待更多数据");
                return;
              }

              // 更新屏幕尺寸
              if (width > 0 && height > 0) {
                screenWidth.value = width;
                screenHeight.value = height;
              }

              // 提取 payload
              const payloadBlob = blob.slice(20, 20 + payloadLen);

              // 根据帧类型处理 payload
              // 在 ws.onmessage 中，处理完整帧
              if (frameType === 1) {
                // 完整帧 - payload 就是图像数据
                const imageBlob = payloadBlob;
                const headerBytes2 = await imageBlob.slice(0, 4).arrayBuffer();
                const headerView2 = new Uint8Array(headerBytes2);

                let mimeType = "image/jpeg";
                if (
                  headerView2[0] === 0x52 &&
                  headerView2[1] === 0x49 &&
                  headerView2[2] === 0x46 &&
                  headerView2[3] === 0x46
                ) {
                  mimeType = "image/webp";
                } else if (headerView2[0] === 0xff && headerView2[1] === 0xd8) {
                  mimeType = "image/jpeg";
                }

                const url = URL.createObjectURL(
                  new Blob([await imageBlob.arrayBuffer()], { type: mimeType }),
                );

                if (
                  screenImage.value &&
                  screenImage.value.startsWith("blob:")
                ) {
                  URL.revokeObjectURL(screenImage.value);
                }
                screenImage.value = url;
              } else if (frameType === 2) {
                // 差异帧 - 需要重建完整图像
                const payloadArray = new Uint8Array(
                  await payloadBlob.arrayBuffer(),
                );
                let offset = 0;
                const regionCount =
                  (payloadArray[offset] << 8) | payloadArray[offset + 1];
                offset += 2;
                const quality = payloadArray[offset];
                offset += 1;

                console.log(`📊 差异帧: ${regionCount}个区域, 质量=${quality}`);

                // TODO: 实现差异帧重建
                // 1. 获取当前显示图像作为基础
                // 2. 解析每个区域的 WebP 数据
                // 3. 将区域绘制到图像上
              } else if (frameType === 3) {
                // 区域帧
                const payloadArray = new Uint8Array(
                  await payloadBlob.arrayBuffer(),
                );
                let offset = 0;
                const regionCount =
                  (payloadArray[offset] << 8) | payloadArray[offset + 1];
                offset += 2;
                const quality = payloadArray[offset];
                offset += 1;
                const bgLen =
                  (payloadArray[offset] << 24) |
                  (payloadArray[offset + 1] << 16) |
                  (payloadArray[offset + 2] << 8) |
                  payloadArray[offset + 3];
                offset += 4;

                // 提取背景图像
                const backgroundData = payloadArray.slice(
                  offset,
                  offset + bgLen,
                );
                offset += bgLen;

                console.log(
                  `📊 区域帧: ${regionCount}个区域, 背景大小=${bgLen}`,
                );

                // TODO: 实现区域帧重建
                // 1. 解码背景图像
                // 2. 解析每个区域的 WebP 数据
                // 3. 将区域绘制到背景上
              }

              // 更新统计
              if (stats.value) {
                stats.value.framesReceived++;
                stats.value.lastFrameTime = Date.now();
              }

              return;
            } catch (err) {
              console.error("二进制数据解析失败:", err);
            }
          }
        }
        // 处理文本消息
        if (typeof event.data === "string") {
          console.log("📩 收到文本消息:", event.data.substring(0, 200));
          const data = JSON.parse(event.data);
          handleMessage(data);
          return;
        }
      } catch (e) {
        console.error("消息处理失败:", e);
      }
    };

    ws.onerror = (error) => {
      clearTimeout(connectionTimeout);
      console.error("❌ WebSocket错误:", error);
      console.error("WebSocket状态:", {
        readyState: ws?.readyState,
        url: ws?.url,
      });

      connecting.value = false;
      ElMessage.error("连接失败，请查看控制台日志");
    };

    ws.onclose = (event) => {
      clearTimeout(connectionTimeout);
      console.log("WebSocket关闭:", {
        code: event.code,
        reason: event.reason,
        wasClean: event.wasClean,
        readyState: ws?.readyState,
        isManualDisconnect: isManualDisconnect,
      });

      isViewing.value = false;
      connecting.value = false;
      stopHeartbeat();
      stopStatsUpdate();

      // 清理屏幕图片URL
      if (screenImage.value && screenImage.value.startsWith("blob:")) {
        URL.revokeObjectURL(screenImage.value);
        screenImage.value = "";
      }

      if (isManualDisconnect) {
        console.log("✅ 主动断开连接，不重连");
        isManualDisconnect = false; // 重置标志
        return; // 直接返回，不执行重连逻辑
      }

      // WebSocket关闭码说明
      const closeCodeMessages = {
        1000: "正常关闭",
        1001: "服务器断开",
        1002: "协议错误",
        1003: "不支持的数据类型",
        1004: "保留",
        1005: "未收到关闭帧",
        1006: "异常关闭",
        1007: "无效的数据帧",
        1008: "策略违规",
        1009: "消息太大",
        1010: "缺少扩展",
        1011: "意外错误",
        1015: "TLS错误",
      };

      const closeMessage =
        closeCodeMessages[event.code] || `未知错误(${event.code})`;

      if (event.reason && event.reason !== "正常关闭") {
        ElMessage.warning(`连接断开: ${event.reason || closeMessage}`);
        attemptReconnect();
      } else if (event.code !== 1000) {
        ElMessage.warning(`连接断开: ${closeMessage}`);
        attemptReconnect();
      }
    };
  } catch (error) {
    console.error("连接失败:", error);
    ElMessage.error("连接失败: " + (error.message || "未知错误"));
    connecting.value = false;
  }
};

const disconnect = () => {
  isManualDisconnect = true;
  if (ws) {
    // ✅ 发送停止查看消息
    sendMessage({
      type: "stop_view",
      timestamp: Date.now(),
    });

    // 再发送 close 消息
    sendMessage({ type: "close" });

    ws.close();
    ws = null;
  }

  isViewing.value = false;
  screenImage.value = "";
  qrCodes.value = [];
  stopHeartbeat();
  stopStatsUpdate();
  reconnectAttempts = 0;

  // 重置统计
  stats.value = {
    framesReceived: 0,
    bytesReceived: 0,
    avgLatency: 0,
    compressionRatio: 100,
    diffRatio: 0,
    regionRatio: 0,
    fpsActual: 0,
    lastFrameTime: 0,
  };
};

const attemptReconnect = () => {
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    ElMessage.error("重连失败，请手动重新连接");
    return;
  }

  reconnectAttempts++;
  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts - 1), 30000);

  ElMessage.info(
    `${delay / 1000}秒后尝试重连... (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`,
  );

  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    if (!isViewing.value && currentEmployeeId.value) {
      connect();
    }
  }, delay);
};

// ==================== 消息处理 ====================
const handleMessage = (data) => {
  const type = data.type;

  console.log("📨 收到消息:", { type, keys: Object.keys(data) });

  // ✅ 支持多种帧类型
  if (type === "frame" || type === "full_frame" || type === "full") {
    handleFrame(data);
  } else if (type === "diff_frame") {
    handleDiffFrame(data);
  } else if (type === "region_frame") {
    handleRegionFrame(data);
  } else if (type === "connected") {
    console.log("连接成功:", data);
  } else if (type === "qr_detected") {
    handleQrDetected(data);
  } else if (type === "heartbeat_ack") {
    const latency = Date.now() - data.timestamp;
    updateLatency(latency);
  } else if (type === "viewer_update") {
    console.log("观众更新:", data.viewers);
  } else if (type === "pong") {
    const latency = Date.now() - data.timestamp;
    updateLatency(latency);
  } else {
    console.log("未知消息类型:", type);
  }
};

const handleFrame = (data) => {
  try {
    console.log("🖼️ ========== 开始处理帧 ==========");
    console.log("📦 帧数据:", {
      type: data.type,
      compressed: data.compressed,
      dataLength: data.data?.length,
      width: data.width,
      height: data.height,
      hasData: !!data.data,
    });

    if (!data.data) {
      console.error("❌ 帧数据为空!");
      return;
    }

    let imageData;
    let decompressed = false;

    // ✅ 处理压缩数据
    if (data.compressed) {
      console.log("🔓 开始解压数据...");
      try {
        // Base64 解码
        const binaryString = atob(data.data);
        console.log(`📦 Base64解码完成: ${binaryString.length} bytes`);

        const compressedData = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          compressedData[i] = binaryString.charCodeAt(i);
        }
        console.log(`🗜️ 压缩数据: ${compressedData.length} bytes`);

        // 检查 pako 是否可用
        if (typeof pako === "undefined") {
          console.error("❌ pako 未定义！请在页面中引入 pako 库");
          ElMessage.error("pako 库未加载，请刷新页面重试");
          return;
        }

        // 解压
        const decompressedData = pako.inflate(compressedData);
        imageData = decompressedData;
        decompressed = true;

        console.log(
          `✅ 解压成功: ${compressedData.length} -> ${decompressedData.length} bytes`,
        );
      } catch (e) {
        console.error("❌ 解压失败:", e);
        // 尝试直接解码
        try {
          const binaryString = atob(data.data);
          imageData = new Uint8Array(binaryString.length);
          for (let i = 0; i < binaryString.length; i++) {
            imageData[i] = binaryString.charCodeAt(i);
          }
          console.log("✅ 使用未压缩数据");
        } catch (e2) {
          console.error("❌ 解码也失败:", e2);
          return;
        }
      }
    } else {
      // 未压缩数据
      console.log("📦 处理未压缩数据...");
      const binaryString = atob(data.data);
      imageData = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        imageData[i] = binaryString.charCodeAt(i);
      }
    }

    // 检查 JPEG 头
    console.log(
      `🔍 检查数据头: 前10字节 = ${Array.from(imageData.slice(0, 10))
        .map((b) => b.toString(16))
        .join(" ")}`,
    );

    if (
      imageData.length > 2 &&
      imageData[0] === 0xff &&
      imageData[1] === 0xd8
    ) {
      console.log("✅ JPEG 格式验证通过");
    } else {
      console.error(
        `❌ 不是JPEG格式! 前两个字节=0x${imageData[0]?.toString(16)} 0x${imageData[1]?.toString(16)}`,
      );
      return;
    }

    // 创建 Blob 并显示
    const blob = new Blob([imageData], { type: "image/jpeg" });
    const url = URL.createObjectURL(blob);
    console.log(`📸 创建图片URL: ${url.substring(0, 50)}...`);

    // 释放之前的 URL
    if (screenImage.value && screenImage.value.startsWith("blob:")) {
      console.log("🗑️ 释放旧URL:", screenImage.value);
      URL.revokeObjectURL(screenImage.value);
    }

    screenImage.value = url;
    console.log("✅ 图片URL已设置到screenImage");

    // 更新尺寸
    if (data.width && data.height) {
      screenWidth.value = data.width;
      screenHeight.value = data.height;
      console.log(`📐 更新尺寸: ${screenWidth.value}x${screenHeight.value}`);
    }

    // 更新统计
    stats.value.framesReceived++;
    stats.value.lastFrameTime = Date.now();

    console.log(`✅ 帧处理完成，共收到 ${stats.value.framesReceived} 帧`);
  } catch (e) {
    console.error("❌ 处理帧失败:", e);
    console.error("错误堆栈:", e.stack);
  }
};

const handleQrDetected = (data) => {
  qrCodes.value = data.qr_codes || [];

  // 显示提示
  ElMessage.info(`检测到 ${qrCodes.value.length} 个二维码`);
};

const updateLatency = (latency) => {
  stats.value.avgLatency = stats.value.avgLatency * 0.7 + latency * 0.3;

  // 动态调整质量（自动优化）
  if (stats.value.avgLatency > 500 && currentQuality.value > 50) {
    // 延迟过高，建议降低质量
    if (currentQuality.value > 60) {
      // 只是建议，不自动修改
    }
  }
};

// ==================== 消息发送 ====================
const sendMessage = (message) => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message));
  }
};

const sendCommand = (command) => {
  sendMessage({
    type: "command",
    command: command.command,
    params: command.params || {},
    target: "client",
    timestamp: Date.now(),
  });
};

// ==================== 心跳和统计 ====================
const startHeartbeat = () => {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      // ✅ 发送心跳消息
      sendMessage({
        type: "heartbeat",
        timestamp: Date.now(),
      });
      console.log("💓 发送心跳");
    }
  }, 15000); // 30秒发送一次心跳
};

const stopHeartbeat = () => {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
};

const startStatsUpdate = () => {
  stopStatsUpdate();
  statsTimer = setInterval(() => {
    // 计算实际帧率
    if (stats.value.lastFrameTime) {
      const now = Date.now();
      const diff = now - stats.value.lastFrameTime;
      if (diff > 0) {
        stats.value.fpsActual = Math.round(1000 / diff);
      }
    }
  }, 1000);
};

const stopStatsUpdate = () => {
  if (statsTimer) {
    clearInterval(statsTimer);
    statsTimer = null;
  }
};

// ==================== 控制命令 ====================
const changeQuality = (value) => {
  sendCommand({
    command: "quality",
    params: { quality: value },
  });
};

const changeFps = (value) => {
  sendCommand({
    command: "fps",
    params: { fps: value },
  });
};

const toggleDiff = (value) => {
  sendCommand({
    command: "diff_enable",
    params: { enable: value },
  });
};

const toggleRegion = (value) => {
  sendCommand({
    command: "region_enable",
    params: { enable: value },
  });
};

const toggleQr = (value) => {
  sendCommand({
    command: "qr_enable",
    params: { enable: value },
  });
};

const takeScreenshot = () => {
  if (!screenImage.value) return;

  screenshotImage.value = screenImage.value;
  screenshotVisible.value = true;
};

const downloadScreenshot = () => {
  const link = document.createElement("a");
  link.href = screenshotImage.value;
  link.download = `screenshot_${currentEmployeeName.value}_${Date.now()}.jpg`;
  link.click();
};

const copyQr = (text) => {
  navigator.clipboard.writeText(text);
  ElMessage.success("已复制到剪贴板");
};

// ==================== 视图控制 ====================
const fullscreen = () => {
  const container = screenContainer.value;
  if (container.requestFullscreen) {
    container.requestFullscreen();
  }
};

const resetView = () => {
  zoom.value = 1;
  panX.value = 0;
  panY.value = 0;
};

const handleZoom = (event) => {
  event.preventDefault();
  const delta = event.deltaY > 0 ? 0.9 : 1.1;
  zoom.value *= delta;
  zoom.value = Math.min(Math.max(zoom.value, 0.5), 3);
};

const startPan = (event) => {
  if (zoom.value <= 1) return;

  isPanning.value = true;
  startPanX.value = event.clientX - panX.value;
  startPanY.value = event.clientY - panY.value;
  screenContainer.value.style.cursor = "grabbing";
};

const pan = (event) => {
  if (!isPanning.value) return;

  panX.value = event.clientX - startPanX.value;
  panY.value = event.clientY - startPanY.value;

  // 边界限制
  if (screenContainer.value) {
    const containerWidth = screenContainer.value.clientWidth;
    const containerHeight = screenContainer.value.clientHeight;
    const wrapperWidth = screenWidth.value * zoom.value;
    const wrapperHeight = screenHeight.value * zoom.value;

    panX.value = Math.min(
      0,
      Math.max(panX.value, containerWidth - wrapperWidth),
    );
    panY.value = Math.min(
      0,
      Math.max(panY.value, containerHeight - wrapperHeight),
    );
  }
};

const stopPan = () => {
  isPanning.value = false;
  if (screenContainer.value) {
    screenContainer.value.style.cursor = "grab";
  }
};

const imageLoaded = () => {
  resetView();
};

const imageError = () => {
  console.error("图像加载失败");
};

// ==================== 生命周期 ====================
onMounted(() => {
  refreshOnlineClients();

  // 每30秒刷新一次在线列表
  const timer = setInterval(refreshOnlineClients, 30000);

  onUnmounted(() => {
    clearInterval(timer);
    disconnect();
    if (reconnectTimer) clearTimeout(reconnectTimer);
  });
});
</script>

<style scoped>
.remote-screen {
  height: calc(100vh - 120px);
  display: flex;
  position: relative;
  background: #1e1e2f;
}

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 10px;
  min-width: 0;
}

.toolbar {
  margin-bottom: 10px;
  display: flex;
  gap: 10px;
  align-items: center;
  background: white;
  padding: 10px;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
  flex-wrap: wrap;
}

.action-buttons {
  margin-left: 10px;
}

.status-info {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

.status-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.advanced-controls {
  margin-bottom: 10px;
  background: white;
  border-radius: 8px;
  overflow: hidden;
}

.control-panel {
  padding: 10px 20px;
}

.control-row {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.control-label {
  width: 80px;
  font-size: 14px;
  color: #666;
}

.control-slider {
  flex: 1;
}

.control-switches {
  display: flex;
  gap: 20px;
}

.stats-text {
  display: flex;
  gap: 20px;
  color: #666;
  font-size: 13px;
}

.screen-container {
  flex: 1;
  background: #2c2c3a;
  border-radius: 8px;
  overflow: hidden;
  position: relative;
  cursor: grab;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.screen-container:active {
  cursor: grabbing;
}

.screen-wrapper {
  transform-origin: 0 0;
  will-change: transform;
  position: relative;
  min-width: 100%;
  min-height: 100%;
}

.screen-image {
  display: block;
  max-width: none;
  pointer-events: none;
}

.screen-placeholder {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #2c2c3a;
}

.loading-mask {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: white;
  gap: 10px;
  z-index: 10;
}

.qr-marker {
  position: absolute;
  border: 2px solid #f56c6c;
  background: rgba(245, 108, 108, 0.2);
  pointer-events: none;
  z-index: 5;
}

.qr-content {
  position: absolute;
  top: -20px;
  left: 0;
  background: #f56c6c;
  color: white;
  font-size: 10px;
  padding: 2px 4px;
  border-radius: 2px;
  white-space: nowrap;
}

.qr-panel {
  position: absolute;
  bottom: 20px;
  right: 20px;
  width: 300px;
  max-height: 300px;
  overflow-y: auto;
  z-index: 20;
}

.qr-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.qr-data {
  font-size: 12px;
  color: #333;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 员工列表样式 */
.employee-list {
  padding: 10px;
  height: calc(100vh - 150px);
  overflow-y: auto;
}

.search-input {
  margin-bottom: 10px;
}

.employee-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: all 0.3s;
  border-radius: 8px;
}

.employee-item:hover {
  background: #f5f7fa;
  transform: translateX(2px);
}

.employee-item.active {
  background: #ecf5ff;
  border-left: 3px solid #409eff;
}

.employee-item.viewing {
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
}

.employee-status {
  width: 30px;
  display: flex;
  justify-content: center;
}

.viewer-badge :deep(.el-badge__content) {
  font-size: 10px;
  padding: 0 4px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #67c23a;
  box-shadow: 0 0 0 2px rgba(103, 194, 58, 0.2);
  animation: pulse 2s infinite;
  display: inline-block;
}

.status-dot.viewing {
  background: #e6a23c;
  animation: none;
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(103, 194, 58, 0.4);
  }
  70% {
    box-shadow: 0 0 0 6px rgba(103, 194, 58, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(103, 194, 58, 0);
  }
}

.employee-info {
  flex: 1;
}

.employee-name {
  font-weight: 500;
  color: #333;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.employee-detail {
  font-size: 12px;
  color: #999;
  display: flex;
  gap: 8px;
  margin-bottom: 4px;
}

.ip {
  color: #409eff;
}

.employee-capabilities {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.drawer-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
}

.online-count {
  font-size: 12px;
  color: #999;
}
</style>
