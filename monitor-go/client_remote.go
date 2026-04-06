// client_remote.go - 企业级远程屏幕模块（完整重构版）
package main

import (
	"bytes"
	"compress/zlib"
	"container/list"
	"crypto/md5"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"image"
	"image/jpeg"
	"math"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/chai2010/webp"
	"github.com/gorilla/websocket"
	"github.com/kbinani/screenshot"
	"golang.org/x/image/draw"
)

// ========== 枚举和常量 ==========

// RemoteState 远程屏幕状态
type RemoteState string

const (
	RemoteStateDisconnected RemoteState = "disconnected"
	RemoteStateConnecting   RemoteState = "connecting"
	RemoteStateConnected    RemoteState = "connected"
	RemoteStateReconnecting RemoteState = "reconnecting"
	RemoteStatePaused       RemoteState = "paused"
)

// ========== 帧类型常量（与后端匹配）==========
// ✅ 在这里添加你的常量
const (
    FrameTypeFull   = 1  // 完整帧
    FrameTypeDiff   = 2  // 差异帧
    FrameTypeRegion = 3  // 区域帧
)

const (
    FrameHeaderVersion = 2   // 协议版本
    FrameHeaderSize    = 20  // 帧头大小
)

// FrameType 帧类型
type FrameType string

const (
	FrameFull      FrameType = "full"
	FrameKey       FrameType = "key"
	FrameDiff      FrameType = "diff"
	FrameRegion    FrameType = "region"
	FrameThumbnail FrameType = "thumbnail"
)

// NetworkQuality 网络质量等级
type NetworkQuality int

const (
	QualityExcellent NetworkQuality = 100
	QualityGood      NetworkQuality = 80
	QualityFair      NetworkQuality = 60
	QualityPoor      NetworkQuality = 40
	QualityBad       NetworkQuality = 20
	QualityTerrible  NetworkQuality = 10
)

// ========== 配置结构 ==========

// RemoteScreenConfig 远程屏幕配置
type RemoteScreenConfig struct {
	Enabled    bool   `json:"enabled"`
	ServerURL  string `json:"server_url"`
	ClientID   string `json:"client_id"`
	EmployeeID string `json:"employee_id"`
	Format     string `json:"format"`

	BaseFPS int `json:"base_fps"`
	MinFPS  int `json:"min_fps"`
	MaxFPS  int `json:"max_fps"`
	IdleFPS int `json:"idle_fps"`

	BaseQuality      int `json:"base_quality"`
	MinQuality       int `json:"min_quality"`
	MaxQuality       int `json:"max_quality"`
	ThumbnailQuality int `json:"thumbnail_quality"`

	BaseWidth      int `json:"base_width"`
	MinWidth       int `json:"min_width"`
	MaxWidth       int `json:"max_width"`
	ThumbnailWidth int `json:"thumbnail_width"`

	EnableAutoAdjust bool    `json:"enable_auto_adjust"`
	BandwidthLimit   int64   `json:"bandwidth_limit"`
	LatencyThreshold int     `json:"latency_threshold"`
	JitterThreshold  int     `json:"jitter_threshold"`

	EnableDiffFrame bool    `json:"enable_diff_frame"`
	DiffThreshold   float64 `json:"diff_threshold"`
	RegionMinArea   int     `json:"region_min_area"`

	ReconnectDelay       int `json:"reconnect_delay"`
	MaxReconnectDelay    int `json:"max_reconnect_delay"`
	MaxReconnectAttempts int `json:"max_reconnect_attempts"`

	FrameBufferSize int `json:"frame_buffer_size"`
	EncodeQueueSize int `json:"encode_queue_size"`
	SendQueueSize   int `json:"send_queue_size"`
}

// DefaultRemoteConfig 默认配置
func DefaultRemoteConfig() *RemoteScreenConfig {
	return &RemoteScreenConfig{
		Enabled:               true,
		Format:                "webp",
		BaseFPS:               5,
		MinFPS:                1,
		MaxFPS:                10,
		IdleFPS:               1,
		BaseQuality:           70,
		MinQuality:            30,
		MaxQuality:            85,
		ThumbnailQuality:      40,
		BaseWidth:             1280,
		MinWidth:              480,
		MaxWidth:              1280,
		ThumbnailWidth:        640,
		EnableAutoAdjust:      true,
		BandwidthLimit:        1024,
		LatencyThreshold:      200,
		JitterThreshold:       50,
		EnableDiffFrame:       true,
		DiffThreshold:         0.05,
		RegionMinArea:         1000,
		ReconnectDelay:        2,
		MaxReconnectDelay:     60,
		MaxReconnectAttempts:  10,
		FrameBufferSize:       3,
		EncodeQueueSize:       5,
		SendQueueSize:         10,
	}
}

// ========== 数据结构 ==========

// Screenshot 截图数据
type Screenshot struct {
	Data      []byte    `json:"data"`
	Width     int       `json:"width"`
	Height    int       `json:"height"`
	Format    string    `json:"format"`
	Quality   int       `json:"quality"`
	Timestamp time.Time `json:"timestamp"`
	Hash      string    `json:"hash"`
	FrameType FrameType `json:"frame_type"`
	Sequence  int64     `json:"sequence"`
}

// DiffRegion 差异区域
type DiffRegion struct {
	X      int    `json:"x"`
	Y      int    `json:"y"`
	Width  int    `json:"width"`
	Height int    `json:"height"`
	Data   []byte `json:"data"`
	Hash   string `json:"hash"`
}

// FrameBuffer 帧缓冲区
type FrameBuffer struct {
	buffer  *list.List
	maxSize int
	mu      sync.RWMutex
}

func NewFrameBuffer(maxSize int) *FrameBuffer {
	return &FrameBuffer{
		buffer:  list.New(),
		maxSize: maxSize,
	}
}

func (f *FrameBuffer) Push(frame *Screenshot) {
	f.mu.Lock()
	defer f.mu.Unlock()

	if f.buffer.Len() >= f.maxSize {
		front := f.buffer.Front()
		f.buffer.Remove(front)
	}
	f.buffer.PushBack(frame)
}

func (f *FrameBuffer) Get() *Screenshot {
	f.mu.RLock()
	defer f.mu.RUnlock()

	if f.buffer.Len() == 0 {
		return nil
	}
	return f.buffer.Back().Value.(*Screenshot)
}

func (f *FrameBuffer) Clear() {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.buffer.Init()
}

// NetworkStats 网络统计
type NetworkStats struct {
	RTTs       []float64
	Jitters    []float64
	Bandwidth  int64
	PacketLoss float64
	Quality    NetworkQuality
	LastUpdate time.Time
	mu         sync.RWMutex
}

func NewNetworkStats() *NetworkStats {
	return &NetworkStats{
		RTTs:      make([]float64, 0, 20),
		Jitters:   make([]float64, 0, 20),
		Bandwidth: 10 * 1024 * 1024,
		Quality:   QualityGood,
	}
}

func (n *NetworkStats) AddRTT(rtt float64) {
	n.mu.Lock()
	defer n.mu.Unlock()

	n.RTTs = append(n.RTTs, rtt)
	if len(n.RTTs) > 20 {
		n.RTTs = n.RTTs[1:]
	}

	if len(n.RTTs) >= 2 {
		jitter := math.Abs(n.RTTs[len(n.RTTs)-1] - n.RTTs[len(n.RTTs)-2])
		n.Jitters = append(n.Jitters, jitter)
		if len(n.Jitters) > 20 {
			n.Jitters = n.Jitters[1:]
		}
	}

	n.updateQuality()
}

func (n *NetworkStats) AddBandwidth(bytes int64, duration time.Duration) {
	n.mu.Lock()
	defer n.mu.Unlock()

	if duration > 0 {
		instantBW := float64(bytes*8) / duration.Seconds()
		n.Bandwidth = int64(float64(n.Bandwidth)*0.7 + instantBW*0.3)
	}
}

func (n *NetworkStats) updateQuality() {
	if len(n.RTTs) == 0 {
		n.Quality = QualityGood
		return
	}

	avgRTT := 0.0
	for _, rtt := range n.RTTs {
		avgRTT += rtt
	}
	avgRTT /= float64(len(n.RTTs))

	avgJitter := 0.0
	if len(n.Jitters) > 0 {
		for _, jitter := range n.Jitters {
			avgJitter += jitter
		}
		avgJitter /= float64(len(n.Jitters))
	}

	switch {
	case avgRTT < 50 && avgJitter < 10:
		n.Quality = QualityExcellent
	case avgRTT < 100 && avgJitter < 20:
		n.Quality = QualityGood
	case avgRTT < 200 && avgJitter < 40:
		n.Quality = QualityFair
	case avgRTT < 500 && avgJitter < 80:
		n.Quality = QualityPoor
	case avgRTT < 1000:
		n.Quality = QualityBad
	default:
		n.Quality = QualityTerrible
	}
}

func (n *NetworkStats) GetAvgRTT() float64 {
	n.mu.RLock()
	defer n.mu.RUnlock()

	if len(n.RTTs) == 0 {
		return 0
	}
	sum := 0.0
	for _, rtt := range n.RTTs {
		sum += rtt
	}
	return sum / float64(len(n.RTTs))
}

func (n *NetworkStats) GetAvgJitter() float64 {
	n.mu.RLock()
	defer n.mu.RUnlock()

	if len(n.Jitters) == 0 {
		return 0
	}
	sum := 0.0
	for _, jitter := range n.Jitters {
		sum += jitter
	}
	return sum / float64(len(n.Jitters))
}

// ========== 屏幕采集器 ==========

// RemoteScreenCapture 屏幕采集器
type RemoteScreenCapture struct {
	displayID int
	width     int
	height    int
	mu        sync.RWMutex
}

func NewRemoteScreenCapture(displayID int) *RemoteScreenCapture {
	return &RemoteScreenCapture{displayID: displayID}
}

func (s *RemoteScreenCapture) Capture() (*image.RGBA, error) {
	img, err := screenshot.CaptureDisplay(s.displayID)
	if err != nil {
		return nil, fmt.Errorf("截图失败: %w", err)
	}
	bounds := img.Bounds()
	s.mu.Lock()
	s.width = bounds.Dx()
	s.height = bounds.Dy()
	s.mu.Unlock()
	return img, nil
}

func (s *RemoteScreenCapture) Resize(img *image.RGBA, targetWidth int) *image.RGBA {
	bounds := img.Bounds()
	width := bounds.Dx()
	height := bounds.Dy()

	if width <= targetWidth {
		return img
	}

	ratio := float64(targetWidth) / float64(width)
	newHeight := int(float64(height) * ratio)

	dst := image.NewRGBA(image.Rect(0, 0, targetWidth, newHeight))
	draw.ApproxBiLinear.Scale(dst, dst.Bounds(), img, img.Bounds(), draw.Over, nil)

	return dst
}

func (s *RemoteScreenCapture) GetSize() (int, int) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.width, s.height
}

// ========== 编码器 ==========

// FrameEncoder 帧编码器
type FrameEncoder struct {
	quality int32
	format  string
	mu      sync.RWMutex
}

func NewFrameEncoder(quality int) *FrameEncoder {
	return &FrameEncoder{
		quality: int32(quality),
		format:  "webp",
	}
}

func (e *FrameEncoder) SetQuality(quality int) {
	atomic.StoreInt32(&e.quality, int32(quality))
}

func (e *FrameEncoder) GetQuality() int {
	return int(atomic.LoadInt32(&e.quality))
}

func (e *FrameEncoder) Encode(img *image.RGBA, format string, quality int) ([]byte, error) {
	var buf bytes.Buffer

	switch format {
	case "webp":
		opts := &webp.Options{
			Lossless: false,
			Quality:  float32(quality),
		}
		if err := webp.Encode(&buf, img, opts); err != nil {
			return nil, err
		}
	case "jpeg", "jpg":
		opts := &jpeg.Options{Quality: quality}
		if err := jpeg.Encode(&buf, img, opts); err != nil {
			return nil, err
		}
	default:
		opts := &webp.Options{
			Lossless: false,
			Quality:  float32(quality),
		}
		if err := webp.Encode(&buf, img, opts); err != nil {
			return nil, err
		}
	}

	return buf.Bytes(), nil
}

func (e *FrameEncoder) EncodeWithCompression(img *image.RGBA, format string, quality int) ([]byte, bool, error) {
	encoded, err := e.Encode(img, format, quality)
	if err != nil {
		return nil, false, err
	}

	compressed := false
	data := encoded
	if len(encoded) > 20*1024 {
		var compBuf bytes.Buffer
		writer := zlib.NewWriter(&compBuf)
		if _, err := writer.Write(encoded); err == nil {
			writer.Close()
			if compBuf.Len() < len(encoded) {
				data = compBuf.Bytes()
				compressed = true
			}
		}
	}

	return data, compressed, nil
}

// ========== 差异检测器 ==========

// DiffDetector 差异检测器
type DiffDetector struct {
	threshold float64
	minArea   int
	lastFrame *image.RGBA
	lastHash  string
	mu        sync.RWMutex
}

func NewDiffDetector(threshold float64, minArea int) *DiffDetector {
	return &DiffDetector{
		threshold: threshold,
		minArea:   minArea,
	}
}

func (d *DiffDetector) Detect(current *image.RGBA) (bool, []DiffRegion, float64) {
	d.mu.RLock()
	last := d.lastFrame
	lastHash := d.lastHash
	d.mu.RUnlock()

	if last == nil {
		return true, nil, 1.0
	}

	currentHash := d.calculateHash(current)
	if currentHash == lastHash {
		return false, nil, 0.0
	}

	if current.Bounds().Dx() != last.Bounds().Dx() ||
		current.Bounds().Dy() != last.Bounds().Dy() {
		return true, nil, 1.0
	}

	sampleRate := 100
	totalPixels := current.Bounds().Dx() * current.Bounds().Dy()
	sampleCount := totalPixels / sampleRate
	if sampleCount < 100 {
		sampleCount = totalPixels
	}

	diffCount := 0
	width := current.Bounds().Dx()
	height := current.Bounds().Dy()

	for y := 0; y < height; y += sampleRate / width {
		for x := 0; x < width; x += sampleRate / height {
			if d.pixelDiff(last, current, x, y) {
				diffCount++
			}
		}
	}

	diffRatio := float64(diffCount) / float64(sampleCount)

	if diffRatio < d.threshold {
		return false, nil, diffRatio
	}

	if diffRatio > 0.5 {
		return true, nil, diffRatio
	}

	regions := []DiffRegion{{
		X:      0,
		Y:      0,
		Width:  width,
		Height: height,
	}}

	return true, regions, diffRatio
}

func (d *DiffDetector) pixelDiff(prev, curr *image.RGBA, x, y int) bool {
	offset := (y-prev.Rect.Min.Y)*prev.Stride + (x-prev.Rect.Min.X)*4
	prevR, prevG, prevB := prev.Pix[offset], prev.Pix[offset+1], prev.Pix[offset+2]

	offset = (y-curr.Rect.Min.Y)*curr.Stride + (x-curr.Rect.Min.X)*4
	currR, currG, currB := curr.Pix[offset], curr.Pix[offset+1], curr.Pix[offset+2]

	diff := int(prevR) - int(currR)
	if diff < 0 {
		diff = -diff
	}
	if diff > 30 {
		return true
	}
	diff = int(prevG) - int(currG)
	if diff < 0 {
		diff = -diff
	}
	if diff > 30 {
		return true
	}
	diff = int(prevB) - int(currB)
	if diff < 0 {
		diff = -diff
	}
	return diff > 30
}

func (d *DiffDetector) calculateHash(img *image.RGBA) string {
	hash := md5.Sum(img.Pix)
	return hex.EncodeToString(hash[:])
}

func (d *DiffDetector) Update(current *image.RGBA) {
	d.mu.Lock()
	defer d.mu.Unlock()

	if current == nil {
		d.lastFrame = nil
		d.lastHash = ""
		return
	}

	d.lastFrame = current
	d.lastHash = d.calculateHash(current)
}

// ========== 自适应控制器 ==========

// AdaptiveController 自适应控制器
type AdaptiveController struct {
	config        *RemoteScreenConfig
	stats         *NetworkStats
	targetFPS     int32
	targetQuality int32
	targetWidth   int32
	idleCount     int32
	lastAdjust    time.Time
	mu            sync.RWMutex
}

func NewAdaptiveController(config *RemoteScreenConfig, stats *NetworkStats) *AdaptiveController {
	return &AdaptiveController{
		config:        config,
		stats:         stats,
		targetFPS:     int32(config.BaseFPS),
		targetQuality: int32(config.BaseQuality),
		targetWidth:   int32(config.BaseWidth),
	}
}

func (a *AdaptiveController) Adjust() (fps int, quality int, width int) {
	a.mu.Lock()
	defer a.mu.Unlock()

	if !a.config.EnableAutoAdjust {
		return int(a.targetFPS), int(a.targetQuality), int(a.targetWidth)
	}

	if time.Since(a.lastAdjust) < 3*time.Second {
		return int(a.targetFPS), int(a.targetQuality), int(a.targetWidth)
	}
	a.lastAdjust = time.Now()

	avgRTT := a.stats.GetAvgRTT()
	avgJitter := a.stats.GetAvgJitter()
	networkQuality := a.stats.Quality

	switch networkQuality {
	case QualityExcellent:
		a.targetFPS = int32(a.config.MaxFPS)
		a.targetQuality = int32(a.config.MaxQuality)
		a.targetWidth = int32(a.config.MaxWidth)
	case QualityGood:
		a.targetFPS = int32(a.config.BaseFPS + 2)
		a.targetQuality = int32(a.config.BaseQuality + 10)
		a.targetWidth = int32(a.config.BaseWidth)
	case QualityFair:
		a.targetFPS = int32(a.config.BaseFPS)
		a.targetQuality = int32(a.config.BaseQuality)
		a.targetWidth = int32(a.config.BaseWidth)
	case QualityPoor:
		a.targetFPS = int32(a.config.BaseFPS - 1)
		if a.targetFPS < int32(a.config.MinFPS) {
			a.targetFPS = int32(a.config.MinFPS)
		}
		a.targetQuality = int32(a.config.MinQuality + 20)
		a.targetWidth = int32(a.config.BaseWidth - 200)
	case QualityBad:
		a.targetFPS = int32(a.config.MinFPS)
		a.targetQuality = int32(a.config.MinQuality + 10)
		a.targetWidth = int32(a.config.MinWidth + 100)
	default:
		a.targetFPS = int32(a.config.MinFPS)
		a.targetQuality = int32(a.config.MinQuality)
		a.targetWidth = int32(a.config.MinWidth)
	}

	if avgRTT > 500 {
		if a.targetFPS > 2 {
			a.targetFPS = 2
		}
		if a.targetQuality > 40 {
			a.targetQuality = 40
		}
	}

	if avgJitter > 100 && a.targetFPS > 3 {
		a.targetFPS = 3
	}

	if atomic.LoadInt32(&a.idleCount) > 10 {
		a.targetFPS = int32(a.config.IdleFPS)
	}

	return int(a.targetFPS), int(a.targetQuality), int(a.targetWidth)
}

func (a *AdaptiveController) RecordIdle(idle bool) {
	if idle {
		atomic.AddInt32(&a.idleCount, 1)
	} else {
		atomic.StoreInt32(&a.idleCount, 0)
	}
}

// ========== 重连管理器 ==========

// ReconnectManager 重连管理器
type ReconnectManager struct {
	attempts    int
	baseDelay   time.Duration
	maxDelay    time.Duration
	maxAttempts int
	lastAttempt time.Time
	mu          sync.Mutex
}

func NewReconnectManager(baseDelay, maxDelay time.Duration, maxAttempts int) *ReconnectManager {
	return &ReconnectManager{
		baseDelay:   baseDelay,
		maxDelay:    maxDelay,
		maxAttempts: maxAttempts,
	}
}

func (r *ReconnectManager) ShouldReconnect() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.attempts < r.maxAttempts
}

func (r *ReconnectManager) GetDelay() time.Duration {
	r.mu.Lock()
	defer r.mu.Unlock()

	delay := r.baseDelay * time.Duration(1<<uint(r.attempts))
	if delay > r.maxDelay {
		delay = r.maxDelay
	}

	jitter := time.Duration(float64(delay) * 0.2 * (float64(time.Now().UnixNano()%1000) / 1000))
	return delay + jitter
}

func (r *ReconnectManager) RecordAttempt() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.attempts++
	r.lastAttempt = time.Now()
}

func (r *ReconnectManager) RecordSuccess() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.attempts = 0
}

func (r *ReconnectManager) Reset() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.attempts = 0
}

// ========== 主类：RemoteScreenManager ==========

// RemoteScreenManager 企业级远程屏幕管理器
type RemoteScreenManager struct {
	config *RemoteScreenConfig
	mu     sync.RWMutex

	conn     *websocket.Conn
	state    RemoteState
	stopChan chan struct{}
	doneChan chan struct{}

	clientID   string
	employeeID string

	viewerCount int32

	currentFPS     int32
	currentQuality int32
	currentWidth   int32

	framesSent     int64
	bytesSent      int64
	framesDropped  int64
	reconnectCount int64
	startTime      time.Time

	encoder      *FrameEncoder
	diffDetector *DiffDetector
	diffMu       sync.RWMutex
	networkStats *NetworkStats
	adaptiveCtrl *AdaptiveController
	reconnectMgr *ReconnectManager
	frameBuffer  *FrameBuffer
	capture      *RemoteScreenCapture

	encodeQueue chan *Screenshot
	sendQueue   chan *Screenshot
	stopQueue   chan struct{}

	wg sync.WaitGroup

	lastPing time.Time
	lastPong time.Time
	pingSeq  int64

	FrameSeq      int64
	lastFrameTime time.Time
	lastKeyframe  time.Time

	perfStats map[string]interface{}
	perfMu    sync.RWMutex

	parent *MonitorClient
}

// buildFrameHeader 构建20字节二进制帧头
func buildFrameHeader(frameType int, frameID int64, timestampMs uint32, payloadLen uint32, width, height int) []byte {
    header := make([]byte, FrameHeaderSize)
    
    // 版本号 (1字节)
    header[0] = FrameHeaderVersion
    
    // 帧类型 (1字节)
    header[1] = byte(frameType)
    
    // 宽度 (2字节, 大端序)
    header[2] = byte(width >> 8)
    header[3] = byte(width & 0xFF)
    
    // 高度 (2字节, 大端序)
    header[4] = byte(height >> 8)
    header[5] = byte(height & 0xFF)
    
    // 保留 (2字节)
    header[6] = 0
    header[7] = 0
    
    // 帧ID (4字节, 大端序)
    header[8] = byte(frameID >> 24)
    header[9] = byte(frameID >> 16)
    header[10] = byte(frameID >> 8)
    header[11] = byte(frameID & 0xFF)
    
    // 时间戳毫秒 (4字节, 大端序)
    header[12] = byte(timestampMs >> 24)
    header[13] = byte(timestampMs >> 16)
    header[14] = byte(timestampMs >> 8)
    header[15] = byte(timestampMs & 0xFF)
    
    // payload长度 (4字节, 大端序)
    header[16] = byte(payloadLen >> 24)
    header[17] = byte(payloadLen >> 16)
    header[18] = byte(payloadLen >> 8)
    header[19] = byte(payloadLen & 0xFF)
    
    return header
}

// NewRemoteScreenManager 创建远程屏幕管理器
func NewRemoteScreenManager(parent *MonitorClient) *RemoteScreenManager {
	config := DefaultRemoteConfig()

	if parent != nil && parent.configManager != nil {
		cfg := parent.configManager
		config.Enabled = cfg.GetBool("enable_remote_screen")
		config.BaseFPS = cfg.GetInt("remote_base_fps")
		if config.BaseFPS <= 0 {
			config.BaseFPS = 5
		}
		config.MinFPS = cfg.GetInt("remote_min_fps")
		if config.MinFPS <= 0 {
			config.MinFPS = 1
		}
		config.MaxFPS = cfg.GetInt("remote_max_fps")
		if config.MaxFPS <= 0 {
			config.MaxFPS = 10
		}
		config.BaseQuality = cfg.GetInt("remote_base_quality")
		if config.BaseQuality <= 0 {
			config.BaseQuality = 70
		}
		config.MinQuality = cfg.GetInt("remote_min_quality")
		if config.MinQuality <= 0 {
			config.MinQuality = 30
		}
		config.MaxQuality = cfg.GetInt("remote_max_quality")
		if config.MaxQuality <= 0 {
			config.MaxQuality = 85
		}
		config.BaseWidth = cfg.GetInt("remote_base_width")
		if config.BaseWidth <= 0 {
			config.BaseWidth = 1280
		}
		config.MinWidth = cfg.GetInt("remote_min_width")
		if config.MinWidth <= 0 {
			config.MinWidth = 640
		}
		config.MaxWidth = cfg.GetInt("remote_max_width")
		if config.MaxWidth <= 0 {
			config.MaxWidth = 1280
		}
		config.Format = cfg.GetString("format")
		if config.Format == "" {
			config.Format = "webp"
		}

		serverURLs := cfg.GetStringSlice("server_urls")
		if len(serverURLs) > 0 {
			config.ServerURL = serverURLs[0]
		}

		config.ClientID = cfg.GetString("client_id")
		config.EmployeeID = cfg.GetString("employee_id")
	}

	r := &RemoteScreenManager{
		config:         config,
		parent:         parent,
		state:          RemoteStateDisconnected,
		stopChan:       make(chan struct{}),
		doneChan:       make(chan struct{}),
		clientID:       config.ClientID,
		employeeID:     config.EmployeeID,
		currentFPS:     int32(config.BaseFPS),
		currentQuality: int32(config.BaseQuality),
		currentWidth:   int32(config.BaseWidth),
		startTime:      time.Now(),
		encodeQueue:    make(chan *Screenshot, config.EncodeQueueSize),
		sendQueue:      make(chan *Screenshot, config.SendQueueSize),
		stopQueue:      make(chan struct{}),
		FrameSeq:       0,
		perfStats:      make(map[string]interface{}),
	}

	r.encoder = NewFrameEncoder(config.BaseQuality)
	r.diffDetector = NewDiffDetector(config.DiffThreshold, config.RegionMinArea)
	r.networkStats = NewNetworkStats()
	r.adaptiveCtrl = NewAdaptiveController(config, r.networkStats)
	r.reconnectMgr = NewReconnectManager(
		time.Duration(config.ReconnectDelay)*time.Second,
		time.Duration(config.MaxReconnectDelay)*time.Second,
		config.MaxReconnectAttempts,
	)
	r.frameBuffer = NewFrameBuffer(config.FrameBufferSize)
	r.capture = NewRemoteScreenCapture(0)

	return r
}

// Start 启动远程屏幕服务
func (r *RemoteScreenManager) Start() {
	if !r.config.Enabled {
		logInfo("远程屏幕未启用")
		return
	}

	if r.clientID == "" {
		logInfo("远程屏幕: clientID为空，等待注册完成")
		return
	}

	r.mu.Lock()
	if r.state != RemoteStateDisconnected {
		r.mu.Unlock()
		return
	}
	r.state = RemoteStateConnecting
	r.mu.Unlock()

	r.wg.Add(4)
	go r.connectLoop()
	go r.encodeLoop()
	go r.sendLoop()
	go r.heartbeatLoop()

	go r.monitorLoop()
	go r.captureLoop()

	logInfo("远程屏幕服务已启动 (FPS=%d, Quality=%d, Width=%d)",
		r.currentFPS, r.currentQuality, r.currentWidth)
}

// Stop 停止远程屏幕服务
func (r *RemoteScreenManager) Stop() {
	r.mu.Lock()
	if r.state == RemoteStateDisconnected {
		r.mu.Unlock()
		return
	}
	r.state = RemoteStateDisconnected
	r.mu.Unlock()

	close(r.stopChan)
	close(r.stopQueue)

	r.mu.Lock()
	if r.conn != nil {
		r.conn.Close()
		r.conn = nil
	}
	r.mu.Unlock()

	done := make(chan struct{})
	go func() {
		r.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		logInfo("远程屏幕服务已停止")
	case <-time.After(10 * time.Second):
		logWarn("远程屏幕停止超时")
	}

	close(r.doneChan)
}

// UpdateIDs 更新身份信息
func (r *RemoteScreenManager) UpdateIDs(clientID, employeeID string) {
	r.mu.Lock()
	r.clientID = clientID
	r.employeeID = employeeID
	r.mu.Unlock()

	if r.config.Enabled && clientID != "" && r.state == RemoteStateDisconnected {
		r.Start()
	}
}

// ========== 连接管理 ==========

func (r *RemoteScreenManager) connectLoop() {
	defer r.wg.Done()

	for {
		select {
		case <-r.stopChan:
			return
		default:
		}

		if !r.reconnectMgr.ShouldReconnect() {
			logError("远程屏幕达到最大重连次数")
			r.mu.Lock()
			r.state = RemoteStateDisconnected
			r.mu.Unlock()
			return
		}

		if err := r.connect(); err != nil {
			logDebug("远程屏幕连接失败: %v", err)
			r.reconnectMgr.RecordAttempt()

			delay := r.reconnectMgr.GetDelay()
			logInfo("%v 后重连...", delay)

			select {
			case <-time.After(delay):
				continue
			case <-r.stopChan:
				return
			}
		}

		r.reconnectMgr.RecordSuccess()
		r.mu.Lock()
		r.state = RemoteStateConnected
		r.mu.Unlock()

		logInfo("远程屏幕 WebSocket 连接成功")

		r.sendClientInfo()

		if err := r.receiveLoop(); err != nil {
			logDebug("远程屏幕接收循环结束: %v", err)
		}

		r.mu.Lock()
		if r.state == RemoteStateConnected {
			r.state = RemoteStateReconnecting
		}
		r.mu.Unlock()

		r.frameBuffer.Clear()
		r.diffMu.Lock()
		if r.diffDetector != nil {
			r.diffDetector.Update(nil)
		}
		r.diffMu.Unlock()

		select {
		case <-time.After(3 * time.Second):
		case <-r.stopChan:
			return
		}
	}
}

func (r *RemoteScreenManager) connect() error {
	r.mu.RLock()
	clientID := r.clientID
	r.mu.RUnlock()

	if clientID == "" {
		return fmt.Errorf("clientID为空")
	}

	var serverURL string
	if r.parent != nil && len(r.parent.serverURLs) > 0 {
		serverURL = r.parent.serverURLs[0]
	} else {
		serverURL = r.config.ServerURL
		if serverURL == "" {
			serverURL = "localhost:8000"
		}
	}

	serverURL = strings.TrimPrefix(serverURL, "http://")
	serverURL = strings.TrimPrefix(serverURL, "https://")

	wsURL := fmt.Sprintf("ws://%s/api/remote/ws/client/%s", serverURL, clientID)

	logDebug("远程屏幕连接: %s", wsURL)

	dialer := websocket.Dialer{
		HandshakeTimeout: 10 * time.Second,
	}

	conn, _, err := dialer.Dial(wsURL, nil)
	if err != nil {
		return err
	}

	r.mu.Lock()
	r.conn = conn
	r.mu.Unlock()

	return nil
}

func (r *RemoteScreenManager) receiveLoop() error {
    for {
        select {
        case <-r.stopChan:
            return nil
        default:
        }

        r.mu.RLock()
        conn := r.conn
        r.mu.RUnlock()

        if conn == nil {
            return nil
        }

        // ✅ 使用 ReadMessage 接收消息（支持文本和二进制）
        msgType, msgData, err := conn.ReadMessage()
        if err != nil {
            return err
        }
        
        // 处理文本消息（命令、心跳响应等）
        if msgType == websocket.TextMessage {
            var msg map[string]interface{}
            if err := json.Unmarshal(msgData, &msg); err != nil {
                logDebug("解析JSON失败: %v", err)
                continue
            }
            r.handleMessage(msg)
        }
        // 二进制消息（如果后端发送二进制，可以在这里处理）
        // else if msgType == websocket.BinaryMessage {
        //     // 处理二进制消息...
        // }
    }
}

func (r *RemoteScreenManager) handleMessage(msg map[string]interface{}) {
	msgType, _ := msg["type"].(string)

	switch msgType {
	case "viewer_update":
		if viewers, ok := msg["viewers"].(float64); ok {
			newCount := int32(viewers)
			oldCount := atomic.SwapInt32(&r.viewerCount, newCount)

			logInfo("远程屏幕观众更新: %d -> %d", oldCount, newCount)

			if newCount > 0 && oldCount == 0 {
				logInfo("远程屏幕: 有观众连接")
				r.diffMu.Lock()
				if r.diffDetector != nil {
					r.diffDetector.lastFrame = nil
					r.diffDetector.lastHash = ""
				}
				r.diffMu.Unlock()
				if r.frameBuffer != nil {
					r.frameBuffer.Clear()
				}
			}
		}

	case "command":
		cmd, _ := msg["command"].(string)
		params, _ := msg["params"].(map[string]interface{})
		r.handleCommand(cmd, params)

	case "connected":
		logInfo("远程屏幕会话建立成功")
		if viewers, ok := msg["viewers"].(float64); ok {
			atomic.StoreInt32(&r.viewerCount, int32(viewers))
		}

	case "pong":
		if _, ok := msg["seq"].(float64); ok {
			latency := float64(time.Since(r.lastPing).Microseconds()) / 1000
			r.networkStats.AddRTT(latency)
		}

	case "close":
		logInfo("远程屏幕收到关闭消息")
		atomic.StoreInt32(&r.viewerCount, 0)
		r.diffMu.Lock()
		if r.diffDetector != nil {
			r.diffDetector.lastFrame = nil
			r.diffDetector.lastHash = ""
		}
		r.diffMu.Unlock()
		if r.frameBuffer != nil {
			r.frameBuffer.Clear()
		}
	}
}

func (r *RemoteScreenManager) handleCommand(cmd string, params map[string]interface{}) {
	switch cmd {
	case "quality":
		if q, ok := params["quality"].(float64); ok {
			newQuality := int(q)
			if newQuality < r.config.MinQuality {
				newQuality = r.config.MinQuality
			}
			if newQuality > r.config.MaxQuality {
				newQuality = r.config.MaxQuality
			}
			atomic.StoreInt32(&r.currentQuality, int32(newQuality))
			r.encoder.SetQuality(newQuality)
			logInfo("远程屏幕画质调整为: %d%%", newQuality)
		}

	case "fps":
		if f, ok := params["fps"].(float64); ok {
			newFPS := int(f)
			if newFPS < r.config.MinFPS {
				newFPS = r.config.MinFPS
			}
			if newFPS > r.config.MaxFPS {
				newFPS = r.config.MaxFPS
			}
			atomic.StoreInt32(&r.currentFPS, int32(newFPS))
			logInfo("远程屏幕帧率调整为: %d fps", newFPS)
		}

	case "width":
		if w, ok := params["width"].(float64); ok {
			newWidth := int(w)
			if newWidth < r.config.MinWidth {
				newWidth = r.config.MinWidth
			}
			if newWidth > r.config.MaxWidth {
				newWidth = r.config.MaxWidth
			}
			atomic.StoreInt32(&r.currentWidth, int32(newWidth))
			logInfo("远程屏幕宽度调整为: %d", newWidth)
		}

	case "reset":
		atomic.StoreInt32(&r.currentFPS, int32(r.config.BaseFPS))
		atomic.StoreInt32(&r.currentQuality, int32(r.config.BaseQuality))
		atomic.StoreInt32(&r.currentWidth, int32(r.config.BaseWidth))
		r.encoder.SetQuality(r.config.BaseQuality)
		logInfo("远程屏幕参数已重置")

	case "pause":
		r.mu.Lock()
		if r.state == RemoteStateConnected {
			r.state = RemoteStatePaused
			logInfo("远程屏幕已暂停")
		}
		r.mu.Unlock()

	case "resume":
		r.mu.Lock()
		if r.state == RemoteStatePaused {
			r.state = RemoteStateConnected
			logInfo("远程屏幕已恢复")
		}
		r.mu.Unlock()

	case "status":
		r.mu.RLock()
		status := map[string]interface{}{
			"state":           r.state,
			"viewer_count":    atomic.LoadInt32(&r.viewerCount),
			"current_fps":     atomic.LoadInt32(&r.currentFPS),
			"current_quality": atomic.LoadInt32(&r.currentQuality),
			"current_width":   atomic.LoadInt32(&r.currentWidth),
			"frames_sent":     atomic.LoadInt64(&r.framesSent),
			"frames_dropped":  atomic.LoadInt64(&r.framesDropped),
		}
		r.mu.RUnlock()

		response := map[string]interface{}{
			"type":    "status_response",
			"command": "status",
			"status":  status,
		}
		r.sendMessage(response)
	}
}

func (r *RemoteScreenManager) sendClientInfo() {
	r.mu.RLock()
	clientID := r.clientID
	employeeID := r.employeeID
	r.mu.RUnlock()

	info := map[string]interface{}{
		"type":        "client_info",
		"timestamp":   time.Now().Unix(),
		"client_id":   clientID,
		"employee_id": employeeID,
		"capabilities": map[string]interface{}{
			"diff_frame":  r.config.EnableDiffFrame,
			"auto_adjust": r.config.EnableAutoAdjust,
			"max_fps":     r.config.MaxFPS,
			"max_quality": r.config.MaxQuality,
			"max_width":   r.config.MaxWidth,
		},
		"system": map[string]interface{}{
			"platform":   runtime.GOOS,
			"go_version": runtime.Version(),
		},
	}

	r.sendMessage(info)
}

func (r *RemoteScreenManager) sendMessage(msg interface{}) error {
	r.mu.RLock()
	conn := r.conn
	r.mu.RUnlock()

	if conn == nil {
		return fmt.Errorf("连接未建立")
	}

	conn.SetWriteDeadline(time.Now().Add(5 * time.Second))
	return conn.WriteJSON(msg)
}

// ========== 截图采集循环 ==========

func (r *RemoteScreenManager) captureLoop() {
	defer r.wg.Done()

	logInfo("远程屏幕采集循环已启动")

	getFrameInterval := func() time.Duration {
		fps := atomic.LoadInt32(&r.currentFPS)
		if fps <= 0 {
			fps = 1
		}
		return time.Second / time.Duration(fps)
	}

	ticker := time.NewTicker(getFrameInterval())
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if atomic.LoadInt32(&r.viewerCount) == 0 {
				continue
			}

			r.mu.RLock()
			state := r.state
			r.mu.RUnlock()

			if state != RemoteStateConnected {
				continue
			}

			currentFPS := atomic.LoadInt32(&r.currentFPS)
			if currentFPS > 0 {
				ticker.Reset(time.Second / time.Duration(currentFPS))
			}

			r.captureAndProcess()

		case <-r.stopChan:
			return
		}
	}
}

// client_remote.go - captureAndProcess 函数

func (r *RemoteScreenManager) captureAndProcess() {
    // 如果没有观众，跳过采集
    if atomic.LoadInt32(&r.viewerCount) == 0 {
        return
    }
    
    img, err := r.capture.Capture()
    if err != nil {
        logDebug("远程屏幕截图失败: %v", err)
        return
    }

    // 调整大小
    targetWidth := int(atomic.LoadInt32(&r.currentWidth))
    if targetWidth <= 0 {
        targetWidth = r.config.BaseWidth
    }
    img = r.capture.Resize(img, targetWidth)

    quality := int(atomic.LoadInt32(&r.currentQuality))
    
    // WebP 编码
    var buf bytes.Buffer
    opts := &webp.Options{
        Lossless: false,
        Quality:  float32(quality),
    }
    if err := webp.Encode(&buf, img, opts); err != nil {
        logDebug("WebP编码失败: %v", err)
        return
    }
    encoded := buf.Bytes()
    
    // 验证 WebP 头
    if len(encoded) < 4 || string(encoded[0:4]) != "RIFF" {
        logError("无效的 WebP 数据")
        return
    }
    
    // ✅ 创建帧（不在这里发送，入队等待处理）
    frame := &Screenshot{
        Data:      encoded,
        Width:     img.Bounds().Dx(),
        Height:    img.Bounds().Dy(),
        Format:    "webp",
        Quality:   quality,
        Timestamp: time.Now(),
        FrameType: FrameFull,
        Sequence:  atomic.AddInt64(&r.FrameSeq, 1),
    }

    // 入队到编码队列
    select {
    case r.encodeQueue <- frame:
        // 成功入队
    default:
        atomic.AddInt64(&r.framesDropped, 1)
        logDebug("编码队列满，丢弃帧 seq=%d", frame.Sequence)
    }
}

// ========== 编码和发送 ==========
func (r *RemoteScreenManager) encodeLoop() {
    defer r.wg.Done()

    logInfo("远程屏幕编码循环已启动")

    for {
        select {
        case screenshot := <-r.encodeQueue:
            if screenshot == nil {
                continue
            }

            // ✅ 这里不需要重新编码，直接传递到发送队列
            // 如果后续需要压缩或其他处理，可以在这里添加
            
            select {
            case r.sendQueue <- screenshot:
                logDebug("帧入队发送: seq=%d, size=%d", screenshot.Sequence, len(screenshot.Data))
            default:
                atomic.AddInt64(&r.framesDropped, 1)
                logDebug("发送队列满，丢弃帧 seq=%d", screenshot.Sequence)
            }

        case <-r.stopQueue:
            return
        }
    }
}

func (r *RemoteScreenManager) sendLoop() {
    defer r.wg.Done()

    logInfo("远程屏幕发送循环已启动")

    for {
        select {
        case screenshot := <-r.sendQueue:
            if screenshot == nil {
                continue
            }

            viewerCount := atomic.LoadInt32(&r.viewerCount)
            
            // 无观众时跳过发送
            if viewerCount == 0 {
                logDebug("无观众，跳过发送帧 seq=%d", screenshot.Sequence)
                continue
            }

            // ✅ 发送二进制帧
            if err := r.sendFrame(screenshot); err != nil {
                logError("发送失败: %v (seq=%d)", err, screenshot.Sequence)
                atomic.AddInt64(&r.framesDropped, 1)
            } else {
                atomic.AddInt64(&r.framesSent, 1)
                atomic.AddInt64(&r.bytesSent, int64(len(screenshot.Data)+FrameHeaderSize))
            }

        case <-r.stopQueue:
            return
        }
    }
}

// client_remote.go - 修复 sendFrame 函数
func (r *RemoteScreenManager) sendFrame(screenshot *Screenshot) error {
    r.mu.RLock()
    conn := r.conn
    r.mu.RUnlock()

    if conn == nil {
        return fmt.Errorf("连接未建立")
    }

    if len(screenshot.Data) == 0 {
        return fmt.Errorf("帧数据为空")
    }

    // ✅ 修复：将字符串帧类型转换为 int
    var frameTypeInt int
    switch screenshot.FrameType {
    case FrameFull:
        frameTypeInt = FrameTypeFull
    case FrameDiff:
        frameTypeInt = FrameTypeDiff
    case FrameRegion:
        frameTypeInt = FrameTypeRegion
    default:
        frameTypeInt = FrameTypeFull
    }
    
    timestampMs := uint32(screenshot.Timestamp.UnixMilli())
    
    header := buildFrameHeader(
        frameTypeInt,           // 使用 int 类型
        screenshot.Sequence,
        timestampMs,
        uint32(len(screenshot.Data)),
        screenshot.Width,
        screenshot.Height,
    )
    
    binaryFrame := append(header, screenshot.Data...)
    
    conn.SetWriteDeadline(time.Now().Add(5 * time.Second))
    
    if err := conn.WriteMessage(websocket.BinaryMessage, binaryFrame); err != nil {
        return fmt.Errorf("发送二进制帧失败: %w", err)
    }
    
    if screenshot.Sequence%30 == 0 {
        logInfo("📤 帧发送成功: seq=%d, type=%d, size=%d, %dx%d",
            screenshot.Sequence, frameTypeInt, len(binaryFrame), screenshot.Width, screenshot.Height)
    }
    
    return nil
}

// ========== 辅助方法 ==========

func (r *RemoteScreenManager) encodeWebP(img *image.RGBA, quality int) ([]byte, error) {
	var buf bytes.Buffer
	opts := &webp.Options{
		Lossless: false,
		Quality:  float32(quality),
	}
	if err := webp.Encode(&buf, img, opts); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func (r *RemoteScreenManager) createImageFromData(data []byte, width, height int) *image.RGBA {
	if data == nil || len(data) == 0 {
		return image.NewRGBA(image.Rect(0, 0, width, height))
	}

	var img image.Image
	var err error

	if len(data) >= 2 && data[0] == 0xff && data[1] == 0xd8 {
		img, err = jpeg.Decode(bytes.NewReader(data))
		if err != nil {
			return image.NewRGBA(image.Rect(0, 0, width, height))
		}
	} else if len(data) >= 4 && string(data[0:4]) == "RIFF" {
		img, err = webp.Decode(bytes.NewReader(data))
		if err != nil {
			return image.NewRGBA(image.Rect(0, 0, width, height))
		}
	} else {
		img, _, err = image.Decode(bytes.NewReader(data))
		if err != nil {
			return image.NewRGBA(image.Rect(0, 0, width, height))
		}
	}

	bounds := img.Bounds()
	rgba := image.NewRGBA(bounds)

	for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
		for x := bounds.Min.X; x < bounds.Max.X; x++ {
			rgba.Set(x, y, img.At(x, y))
		}
	}

	return rgba
}

// ========== 心跳和监控 ==========

func (r *RemoteScreenManager) heartbeatLoop() {
	defer r.wg.Done()

	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			r.lastPing = time.Now()

			ping := map[string]interface{}{
				"type":      "ping",
				"seq":       atomic.AddInt64(&r.pingSeq, 1),
				"timestamp": time.Now().Unix(),
				"client_id": r.clientID,
			}

			_ = r.sendMessage(ping)

		case <-r.stopChan:
			return
		}
	}
}

func (r *RemoteScreenManager) monitorLoop() {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			r.updatePerformanceStats()

			if r.config.EnableAutoAdjust && atomic.LoadInt32(&r.viewerCount) > 0 {
				fps, quality, width := r.adaptiveCtrl.Adjust()
				atomic.StoreInt32(&r.currentFPS, int32(fps))
				atomic.StoreInt32(&r.currentQuality, int32(quality))
				atomic.StoreInt32(&r.currentWidth, int32(width))
				r.encoder.SetQuality(quality)
			}

		case <-r.stopChan:
			return
		}
	}
}

func (r *RemoteScreenManager) updatePerformanceStats() {
	r.perfMu.Lock()
	defer r.perfMu.Unlock()

	r.perfStats["frames_sent"] = atomic.LoadInt64(&r.framesSent)
	r.perfStats["bytes_sent"] = atomic.LoadInt64(&r.bytesSent)
	r.perfStats["frames_dropped"] = atomic.LoadInt64(&r.framesDropped)
	r.perfStats["viewer_count"] = atomic.LoadInt32(&r.viewerCount)
	r.perfStats["current_fps"] = atomic.LoadInt32(&r.currentFPS)
	r.perfStats["current_quality"] = atomic.LoadInt32(&r.currentQuality)
	r.perfStats["current_width"] = atomic.LoadInt32(&r.currentWidth)
	r.perfStats["avg_rtt"] = r.networkStats.GetAvgRTT()
	r.perfStats["network_quality"] = r.networkStats.Quality
	r.perfStats["state"] = r.state
}

// ========== 外部接口 ==========

// GetStatus 获取状态
func (r *RemoteScreenManager) GetStatus() RemoteStatus {
	r.perfMu.RLock()
	defer r.perfMu.RUnlock()

	return RemoteStatus{
		State:          r.state,
		ViewerCount:    int(atomic.LoadInt32(&r.viewerCount)),
		CurrentFPS:     int(atomic.LoadInt32(&r.currentFPS)),
		CurrentQuality: int(atomic.LoadInt32(&r.currentQuality)),
		CurrentWidth:   int(atomic.LoadInt32(&r.currentWidth)),
		FramesSent:     atomic.LoadInt64(&r.framesSent),
		BytesSent:      atomic.LoadInt64(&r.bytesSent),
		DroppedFrames:  atomic.LoadInt64(&r.framesDropped),
		NetworkQuality: int(r.networkStats.Quality),
	}
}

// RemoteStatus 远程屏幕状态
type RemoteStatus struct {
	State          RemoteState `json:"state"`
	ViewerCount    int         `json:"viewer_count"`
	CurrentFPS     int         `json:"current_fps"`
	CurrentQuality int         `json:"current_quality"`
	CurrentWidth   int         `json:"current_width"`
	FramesSent     int64       `json:"frames_sent"`
	BytesSent      int64       `json:"bytes_sent"`
	DroppedFrames  int64       `json:"dropped_frames"`
	NetworkQuality int         `json:"network_quality"`
}