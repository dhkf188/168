<!-- admin_Attendance.vue - 完整修复版 -->
<template>
  <div class="attendance-management">
    <el-tabs v-model="activeTab">
      <!-- 考勤记录选项卡 -->
      <el-tab-pane label="考勤记录" name="attendance">
        <!-- 在考勤记录选项卡的 filter-card 中添加 -->
        <el-card class="filter-card" shadow="hover">
          <el-row :gutter="20" align="middle">
            <el-col :span="4">
              <el-date-picker
                v-model="filters.yearMonth"
                type="month"
                placeholder="选择月份"
                format="YYYY年MM月"
                value-format="YYYY-MM"
                @change="handleMonthChange"
                style="width: 100%"
              />
            </el-col>
            <el-col :span="4">
              <el-input
                v-model="filters.searchKeyword"
                placeholder="搜索员工姓名"
                clearable
                :prefix-icon="Search"
                @input="handleSearch"
              />
            </el-col>
            <el-col :span="2">
              <!-- ✅ 添加自动保存开关 -->
              <el-switch
                v-model="autoSaveEnabled"
                active-text="自动"
                inactive-text="手动"
                @change="handleAutoSaveToggle"
              />
            </el-col>
            <el-col :span="8">
              <div class="batch-actions">
                <el-button type="primary" size="small" @click="toggleSelectAll"
                  ><el-icon><Select /></el-icon
                  >{{ isAllSelected ? "取消全选" : "全选" }}</el-button
                >
                <el-button
                  type="success"
                  size="small"
                  @click="openBatchDialog"
                  :disabled="selectedEmployees.length === 0"
                  ><el-icon><Edit /></el-icon>批量操作 ({{
                    selectedEmployees.length
                  }})</el-button
                >
                <el-button
                  type="danger"
                  size="small"
                  @click="batchDeleteEmployees"
                  :disabled="selectedEmployees.length === 0"
                  ><el-icon><Delete /></el-icon>批量删除</el-button
                >
              </div>
            </el-col>
            <el-col :span="6" class="text-right">
              <el-button @click="refreshAttendanceData" :loading="refreshing">
                <el-icon><Refresh /></el-icon>刷新
              </el-button>
              <el-button type="primary" @click="showAddEmployeeDialog"
                ><el-icon><Plus /></el-icon>添加员工</el-button
              >
              <!-- ✅ 手动保存按钮，当自动保存关闭时显示 -->
              <el-button
                v-if="!autoSaveEnabled"
                type="success"
                @click="saveAllAttendance"
                :loading="saving"
                ><el-icon><Check /></el-icon>保存全部</el-button
              >
              <el-button @click="exportAttendanceTable"
                ><el-icon><Download /></el-icon>导出</el-button
              >
            </el-col>
          </el-row>
        </el-card>

        <!-- 考勤汇总卡片
        <el-card class="summary-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span
                ><el-icon><DataLine /></el-icon>考勤汇总</span
              >
              <el-button
                type="primary"
                link
                size="small"
                @click="refreshSummary"
                >刷新</el-button
              >
            </div>
          </template>
          <el-row :gutter="20">
            <el-col :span="6">
              <div class="stat-item">
                <div class="stat-value">{{ summaryStats.totalEmployees }}</div>
                <div class="stat-label">总员工数</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-item">
                <div class="stat-value">{{ summaryStats.totalWorkDays }}</div>
                <div class="stat-label">总出勤天数</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-item">
                <div class="stat-value">
                  {{ summaryStats.totalLeaveRestDays }}
                </div>
                <div class="stat-label">总请假/休假天数</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-item">
                <div class="stat-value">
                  {{ summaryStats.avgAttendanceRate }}%
                </div>
                <div class="stat-label">平均出勤率</div>
              </div>
            </el-col>
          </el-row>
        </el-card> -->

        <el-card
          class="attendance-table-card"
          shadow="hover"
          v-loading="loading"
        >
          <template #header>
            <div class="card-header">
              <div class="card-header-left">
                <span>
                  <el-icon><Calendar /></el-icon>考勤表
                  {{ filters.yearMonth || "请选择月份" }}
                </span>
                <div class="header-stats">
                  <el-tag type="primary" size="small" effect="plain">
                    总员工: {{ summaryStats.totalEmployees }}
                  </el-tag>
                  <el-tag
                    :type="
                      getAttendanceRateType(summaryStats.avgAttendanceRate)
                    "
                    size="small"
                    effect="plain"
                  >
                    出勤率: {{ summaryStats.avgAttendanceRate }}%
                  </el-tag>
                  <el-tag
                    v-if="selectedEmployees.length"
                    type="warning"
                    size="small"
                    effect="plain"
                  >
                    已选择 {{ selectedEmployees.length }} 名员工
                  </el-tag>
                </div>
              </div>
              <div class="legend">
                <span class="legend-item"
                  ><span class="dot work"></span>出勤</span
                >
                <span class="legend-item"
                  ><span class="dot rest-half"></span>休假半天(半休)</span
                >
                <span class="legend-item"
                  ><span class="dot rest-full"></span>休假一天(全休)</span
                >
                <span class="legend-item"
                  ><span class="dot leave"></span>请假半天(半假)</span
                >
                <span class="legend-item"
                  ><span class="dot off-post"></span>请假一天(全假)</span
                >
                <span class="legend-item"
                  ><span class="dot absent"></span>旷工</span
                >
                <span class="legend-item"
                  ><span class="dot resigned"></span>离职</span
                >
              </div>
            </div>
          </template>

          <div class="table-container-fixed-left">
            <table class="unified-table" cellspacing="0" cellpadding="0">
              <thead>
                <tr>
                  <!-- 固定列 -->
                  <th class="checkbox-col fixed-col">
                    <el-checkbox
                      :model-value="isAllSelected"
                      :indeterminate="isIndeterminate"
                      @change="toggleSelectAll"
                    />
                  </th>
                  <th class="date-col fixed-col">入职日期</th>
                  <th class="name-col fixed-col">姓名</th>
                  <th class="position-col fixed-col">岗位</th>
                  <th class="location-col fixed-col">办公地点</th>
                  <th class="stat-col fixed-col">实际上班</th>
                  <th class="stat-col fixed-col">请假/休假天数</th>
                  <!-- 滚动列 -->
                  <th
                    v-for="day in actualDays"
                    :key="day"
                    class="day-col scroll-col"
                    :style="{ minWidth: dayWidth }"
                  >
                    {{ day }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="employee in filteredEmployees" :key="employee.id">
                  <!-- 固定列 -->
                  <td class="checkbox-col fixed-col">
                    <el-checkbox
                      :model-value="selectedEmployees.includes(employee.id)"
                      @change="toggleSelectEmployee(employee.id)"
                    />
                  </td>
                  <td class="date-col fixed-col">
                    {{ formatDate(employee.hire_date) }}
                  </td>
                  <td class="name-col fixed-col">
                    <span
                      class="employee-name-link"
                      @click="showEmployeeDetail(employee)"
                      >{{ employee.name }}</span
                    >
                  </td>
                  <td class="position-col fixed-col">
                    {{ employee.position || "-" }}
                  </td>
                  <td class="location-col fixed-col">
                    <span class="location-text">{{
                      employee.work_location || "现场"
                    }}</span>
                  </td>
                  <td class="stat-col fixed-col">
                    <span class="stat-value work-days">{{
                      getWorkDays(employee)
                    }}</span>
                  </td>
                  <td class="stat-col fixed-col">
                    <span class="stat-value rest-days">{{
                      getLeaveRestDays(employee)
                    }}</span>
                  </td>
                  <!-- 滚动列 -->
                  <td
                    v-for="day in actualDays"
                    :key="day"
                    class="day-cell scroll-col"
                    :class="{ weekend: isWeekend(day) }"
                    :style="{ minWidth: dayWidth }"
                    @click="openStatusDialog(employee, day)"
                  >
                    <span
                      :class="[
                        'status-badge',
                        getStatusClass(getDayStatus(employee, day)),
                      ]"
                    >
                      {{ getStatusText(getDayStatus(employee, day)) }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="actualDays.length > 15" class="scroll-hint">
            <el-icon><ArrowRight /></el-icon> 横向滚动查看更多日期
          </div>

          <div class="employee-pagination">
            <el-pagination
              v-model:current-page="employeePage"
              v-model:page-size="employeePageSize"
              :page-sizes="[10, 20, 50, 100]"
              :total="employeeTotal"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="handleEmployeeSizeChange"
              @current-change="handleEmployeeCurrentChange"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <!-- 绩效考核选项卡 -->
      <el-tab-pane label="绩效考核" name="performance">
        <el-card class="performance-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span
                ><el-icon><TrendCharts /></el-icon>绩效考核</span
              >
              <div class="header-actions">
                <el-date-picker
                  v-model="performanceMonth"
                  type="month"
                  placeholder="选择考核月份"
                  format="YYYY年MM月"
                  value-format="YYYY-MM"
                  @change="loadPerformanceData"
                  style="width: 150px"
                />
                <el-input
                  v-model="performanceSearch"
                  placeholder="搜索员工"
                  clearable
                  style="width: 150px"
                  :prefix-icon="Search"
                />
                <el-button type="primary" @click="showAddScoreDialog"
                  ><el-icon><Plus /></el-icon>添加绩效分</el-button
                >
                <el-button
                  type="success"
                  @click="savePerformance"
                  :loading="savingPerformance"
                  ><el-icon><Check /></el-icon>保存考核</el-button
                >
                <el-button @click="exportPerformance"
                  ><el-icon><Download /></el-icon>导出</el-button
                >
              </div>
            </div>
          </template>

          <el-alert
            title="考核说明"
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 20px"
          >
            <template #default>
              <ul style="margin: 0; padding-left: 20px">
                <li>基础分10分，表现优秀突出可在此加分,工作失误则扣分</li>
              </ul>
            </template>
          </el-alert>

          <el-table :data="filteredPerformanceData" stripe border>
            <el-table-column type="index" label="序号" width="60" />
            <el-table-column prop="employee_name" label="姓名" min-width="100">
              <template #default="{ row }"
                ><span
                  class="employee-name-link"
                  @click="showEmployeeDetailFromPerformance(row)"
                  >{{ row.employee_name }}</span
                ></template
              >
            </el-table-column>
            <el-table-column prop="position" label="岗位" min-width="100" />
            <el-table-column
              prop="base_score"
              label="基础分"
              width="80"
              align="center"
            >
              <template #default
                ><el-tag type="info" size="small">10分</el-tag></template
              >
            </el-table-column>
            <el-table-column label="绩效记录" min-width="300">
              <template #default="{ row }">
                <div class="score-records">
                  <div
                    v-for="(record, idx) in row.score_records"
                    :key="idx"
                    class="score-record-item"
                  >
                    <span class="record-date">{{ record.date }}</span>
                    <span
                      :class="record.score >= 0 ? 'score-plus' : 'score-minus'"
                      >{{
                        record.score >= 0
                          ? `+${record.score}`
                          : `${record.score}`
                      }}分</span
                    >
                    <span class="record-reason">{{ record.reason }}</span>
                    <el-button
                      link
                      type="danger"
                      size="small"
                      @click="deleteScoreRecord(row, idx)"
                      ><el-icon><Delete /></el-icon
                    ></el-button>
                  </div>
                  <!-- <el-button
                    link
                    type="primary"
                    size="small"
                    @click="showAddScoreDialogForEmployee(row)"
                    ><el-icon><Plus /></el-icon>添加加减分</el-button
                  > -->
                </div>
              </template>
            </el-table-column>
            <el-table-column
              prop="total_score"
              label="结余分数"
              width="100"
              align="center"
            >
              <template #default="{ row }"
                ><el-tag :type="getScoreType(row.total_score)" size="large"
                  >{{ row.total_score }}分</el-tag
                ></template
              >
            </el-table-column>
            <el-table-column label="评级" width="100" align="center">
              <template #default="{ row }"
                ><el-tag :type="getGradeType(row.grade)">{{
                  row.grade
                }}</el-tag></template
              >
            </el-table-column>
            <el-table-column label="操作" width="80" align="center">
              <template #default="{ row }">
                <el-button
                  link
                  type="primary"
                  size="small"
                  @click="showAddScoreDialogForEmployee(row)"
                  ><el-icon><Edit /></el-icon>加减分</el-button
                >
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- 罚款管理选项卡 -->
      <el-tab-pane label="罚款详情" name="penalty">
        <el-card class="penalty-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span
                ><el-icon><Warning /></el-icon>罚款详情</span
              >
              <div class="header-actions">
                <el-input
                  v-model="penaltySearchEmployee"
                  placeholder="搜索员工"
                  clearable
                  style="width: 150px; margin-right: 10px"
                  :prefix-icon="Search"
                />
                <el-date-picker
                  v-model="penaltyMonth"
                  type="month"
                  placeholder="选择月份"
                  format="YYYY年MM月"
                  value-format="YYYY-MM"
                  @change="loadPenaltyData"
                  style="width: 150px; margin-right: 10px"
                />
                <el-button type="primary" @click="showAddPenaltyDialog"
                  ><el-icon><Plus /></el-icon>添加罚款</el-button
                >
                <el-button @click="exportPenalty"
                  ><el-icon><Download /></el-icon>导出</el-button
                >
              </div>
            </div>
          </template>

          <el-row :gutter="20" class="penalty-stats-row">
            <el-col :span="6"
              ><el-card class="penalty-stat-card" shadow="hover"
                ><div class="stat-content">
                  <div
                    class="stat-icon"
                    style="background: #e6f7ff; color: #1890ff"
                  >
                    <el-icon><Money /></el-icon>
                  </div>
                  <div class="stat-info">
                    <div class="stat-value">
                      ¥{{ penaltyStats.totalAmount }}
                    </div>
                    <div class="stat-label">总罚款金额</div>
                  </div>
                </div></el-card
              ></el-col
            >
            <el-col :span="6"
              ><el-card class="penalty-stat-card" shadow="hover"
                ><div class="stat-content">
                  <div
                    class="stat-icon"
                    style="background: #f6ffed; color: #52c41a"
                  >
                    <el-icon><User /></el-icon>
                  </div>
                  <div class="stat-info">
                    <div class="stat-value">
                      {{ penaltyStats.employeeCount }}
                    </div>
                    <div class="stat-label">涉及员工</div>
                  </div>
                </div></el-card
              ></el-col
            >
            <el-col :span="6"
              ><el-card class="penalty-stat-card" shadow="hover"
                ><div class="stat-content">
                  <div
                    class="stat-icon"
                    style="background: #fff7e6; color: #fa8c16"
                  >
                    <el-icon><Document /></el-icon>
                  </div>
                  <div class="stat-info">
                    <div class="stat-value">{{ penaltyStats.recordCount }}</div>
                    <div class="stat-label">罚款记录数</div>
                  </div>
                </div></el-card
              ></el-col
            >
            <el-col :span="6"
              ><el-card class="penalty-stat-card" shadow="hover"
                ><div class="stat-content">
                  <div
                    class="stat-icon"
                    style="background: #f9f0ff; color: #722ed1"
                  >
                    <el-icon><TrendCharts /></el-icon>
                  </div>
                  <div class="stat-info">
                    <div class="stat-value">¥{{ penaltyStats.avgAmount }}</div>
                    <div class="stat-label">人均罚款</div>
                  </div>
                </div></el-card
              ></el-col
            >
          </el-row>

          <el-table :data="filteredPenaltyRecords" stripe border>
            <el-table-column type="index" width="50" />
            <el-table-column
              prop="employee_name"
              label="员工姓名"
              min-width="100"
            >
              <template #default="{ row }"
                ><span
                  class="employee-name-link"
                  @click="showEmployeeDetailFromPenalty(row)"
                  >{{ row.employee_name }}</span
                ></template
              >
            </el-table-column>
            <el-table-column prop="position" label="岗位" width="100" />
            <el-table-column prop="penalty_date" label="罚款日期" width="120" />
            <el-table-column
              prop="amount"
              label="金额(元)"
              width="100"
              align="center"
              ><template #default="{ row }"
                ><span class="penalty-amount">¥{{ row.amount }}</span></template
              ></el-table-column
            >
            <el-table-column
              prop="category"
              label="罚款类型"
              width="120"
              align="center"
            >
              <template #default="{ row }"
                ><el-tag
                  :type="getPenaltyCategoryType(row.category)"
                  size="small"
                  >{{ row.category }}</el-tag
                ></template
              >
            </el-table-column>
            <el-table-column
              prop="reason"
              label="罚款原因"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column prop="created_by" label="记录人" width="100" />
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }"
                ><el-button link type="danger" @click="deletePenalty(row)"
                  ><el-icon><Delete /></el-icon>删除</el-button
                ></template
              >
            </el-table-column>
          </el-table>
          <div class="pagination" v-if="penaltyTotal > 0">
            <el-pagination
              v-model:current-page="penaltyPage"
              v-model:page-size="penaltyPageSize"
              :total="penaltyTotal"
              layout="total, sizes, prev, pager, next"
              @size-change="loadPenaltyData"
              @current-change="loadPenaltyData"
            />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 单个考勤状态选择对话框 -->
    <el-dialog
      v-model="statusDialogVisible"
      title="设置考勤状态"
      width="300px"
      @close="resetStatusForm"
    >
      <el-form label-width="80px">
        <el-form-item label="员工">
          <span>{{ currentStatusEmployee?.name }}</span>
        </el-form-item>
        <el-form-item label="日期">
          <span>{{ currentStatusDate }}</span>
        </el-form-item>
        <el-form-item label="考勤状态">
          <el-radio-group v-model="tempStatus">
            <el-radio value="work">✅ 出勤</el-radio>
            <el-radio value="rest_half">🌙 半休</el-radio>
            <el-radio value="rest_full">🌙🌙 全休</el-radio>
            <el-radio value="leave">📝 半假</el-radio>
            <el-radio value="off_post">📝📝 全假</el-radio>
            <el-radio value="absent">❌ 旷工</el-radio>
            <el-radio value="resigned">📄 离职</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="statusDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          @click="confirmStatusChange"
          :loading="statusChanging"
        >
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- 添加/编辑员工对话框 -->
    <el-dialog
      v-model="employeeDialogVisible"
      :title="employeeDialogTitle"
      width="500px"
    >
      <el-form
        :model="employeeForm"
        :rules="employeeRules"
        ref="employeeFormRef"
        label-width="100px"
      >
        <el-form-item label="姓名" prop="name"
          ><el-input v-model="employeeForm.name" placeholder="请输入姓名"
        /></el-form-item>
        <el-form-item label="员工ID" prop="employee_id"
          ><el-input
            v-model="employeeForm.employee_id"
            placeholder="请输入员工ID"
        /></el-form-item>
        <el-form-item label="岗位" prop="position"
          ><el-input v-model="employeeForm.position" placeholder="请输入岗位"
        /></el-form-item>
        <el-form-item label="入职日期" prop="hire_date"
          ><el-date-picker
            v-model="employeeForm.hire_date"
            type="date"
            placeholder="选择入职日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
        /></el-form-item>
        <el-form-item label="办公地点" prop="work_location"
          ><el-select
            v-model="employeeForm.work_location"
            filterable
            allow-create
            default-first-option
            placeholder="请选择或输入办公地点"
            style="width: 100%"
            ><el-option label="现场" value="现场" /><el-option
              label="越南/居家"
              value="越南/居家" /><el-option
              label="缅甸/居家"
              value="缅甸/居家" /></el-select
        ></el-form-item>
      </el-form>
      <template #footer
        ><el-button @click="employeeDialogVisible = false">取消</el-button
        ><el-button
          type="primary"
          @click="submitEmployee"
          :loading="submittingEmployee"
          >确定</el-button
        ></template
      >
    </el-dialog>

    <!-- 员工详情对话框 -->
    <!-- 员工详细信息对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="员工详细信息"
      width="580px"
      class="employee-detail-dialog"
      :close-on-click-modal="false"
    >
      <!-- 头像和基本信息头部 -->
      <div class="detail-header">
        <div class="avatar-section">
          <el-avatar :size="64" :icon="User" class="employee-avatar" />
          <div class="employee-title">
            <h3 class="employee-name">{{ currentEmployee?.name }}</h3>
            <div class="employee-badges">
              <el-tag size="small" type="primary">{{
                currentEmployee?.position || "员工"
              }}</el-tag>
              <el-tag
                size="small"
                :type="
                  currentEmployee?.work_location === '现场'
                    ? 'success'
                    : 'warning'
                "
              >
                {{ currentEmployee?.work_location || "现场" }}
              </el-tag>
            </div>
          </div>
        </div>
        <div class="employee-id">
          <el-icon><OfficeBuilding /></el-icon>
          <span>ID: {{ currentEmployee?.employee_id }}</span>
        </div>
      </div>

      <el-divider style="margin: 12px 0" />

      <!-- 使用网格布局 -->
      <div class="detail-grid">
        <!-- 入职信息 -->
        <div class="grid-item">
          <div class="grid-icon">
            <el-icon><Calendar /></el-icon>
          </div>
          <div class="grid-content">
            <div class="grid-label">入职日期</div>
            <div class="grid-value">
              {{ formatDate(currentEmployee?.hire_date) }}
            </div>
          </div>
        </div>

        <!-- 考勤统计 -->
        <div class="grid-item">
          <div class="grid-icon">
            <el-icon><DataLine /></el-icon>
          </div>
          <div class="grid-content">
            <div class="grid-label">本月考勤</div>
            <div class="grid-value">
              <span class="stat-work"
                >{{ getWorkDays(currentEmployee) }}天</span
              >
              <span class="stat-divider">/</span>
              <span class="stat-leave"
                >{{ getLeaveRestDays(currentEmployee) }}天</span
              >
            </div>
          </div>
        </div>

        <!-- 绩效 -->
        <div class="grid-item">
          <div class="grid-icon">
            <el-icon><TrendCharts /></el-icon>
          </div>
          <div class="grid-content">
            <div class="grid-label">本月绩效</div>
            <div class="grid-value">
              <el-tag
                :type="getScoreType(currentPerformance?.total_score || 10)"
                size="small"
                effect="dark"
              >
                {{ currentPerformance?.total_score || 10 }}分
              </el-tag>
              <el-tag
                :type="getGradeType(currentPerformance?.grade || '合格')"
                size="small"
              >
                {{ currentPerformance?.grade || "合格" }}
              </el-tag>
              <el-button
                v-if="hasPermission('attendance:edit')"
                class="add-score-btn"
                size="small"
                @click="showScoreDialogFromDetail"
              >
                <el-icon><Plus /></el-icon>
                <span>添加绩效分</span>
              </el-button>
            </div>
          </div>
        </div>

        <!-- 罚款 -->
        <div class="grid-item">
          <div class="grid-icon">
            <el-icon><Money /></el-icon>
          </div>
          <div class="grid-content">
            <div class="grid-label">本月罚款</div>
            <div class="grid-value">
              <span :class="currentPenaltyTotal > 0 ? 'penalty-amount' : ''">
                ¥{{ currentPenaltyTotal }}
              </span>
              <el-button
                v-if="hasPermission('attendance:edit')"
                class="add-penalty-btn"
                size="small"
                @click="showPenaltyDialogFromDetail"
              >
                <el-icon><Plus /></el-icon>
                <span>添加罚款</span>
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 绩效记录区域 - 只在有记录时显示 -->
      <div v-if="currentPerformance?.score_records?.length > 0">
        <el-divider style="margin: 12px 0">
          <span class="divider-text">绩效记录</span>
        </el-divider>

        <div class="record-section has-records">
          <div class="record-list">
            <div
              v-for="(record, idx) in currentPerformance.score_records.slice(
                -8,
              )"
              :key="idx"
              class="record-item score-item"
            >
              <div class="record-date-badge">
                <span class="record-day">{{
                  formatDateShort(record.date)
                }}</span>
              </div>
              <div class="record-content">
                <span
                  :class="[
                    'record-score',
                    record.score >= 0 ? 'score-plus' : 'score-minus',
                  ]"
                >
                  {{
                    record.score >= 0 ? `+${record.score}` : `${record.score}`
                  }}分
                </span>
                <span class="record-reason">{{ record.reason }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 查看全部按钮 -->
        <div
          class="view-all-actions"
          v-if="(currentPerformance?.score_records?.length || 0) > 8"
        >
          <el-button link type="primary" @click="viewAllScoreRecords">
            查看全部
            {{ currentPerformance?.score_records?.length || 0 }} 条绩效记录
            <el-icon><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>

      <!-- 罚款记录区域 - 只在有记录时显示 -->
      <div v-if="currentPenaltyRecords.length > 0">
        <el-divider style="margin: 12px 0">
          <span class="divider-text">罚款记录</span>
        </el-divider>

        <div class="record-section has-records">
          <div class="record-list">
            <div
              v-for="(record, idx) in currentPenaltyRecords.slice(-5)"
              :key="idx"
              class="record-item penalty-item"
            >
              <div class="record-date-badge penalty-date">
                <span>{{ record.penalty_date }}</span>
              </div>
              <div class="record-content">
                <span class="penalty-amount-badge">¥{{ record.amount }}</span>
                <span class="record-reason">{{ record.reason }}</span>
                <span class="record-category" v-if="record.category">
                  <el-tag
                    size="small"
                    :type="getPenaltyCategoryType(record.category)"
                    effect="plain"
                  >
                    {{ record.category }}
                  </el-tag>
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- 查看全部按钮 -->
        <div class="view-all-actions" v-if="currentPenaltyRecords.length > 5">
          <el-button link type="primary" @click="viewAllPenaltyRecords">
            查看全部 {{ currentPenaltyRecords.length }} 条罚款记录
            <el-icon><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="detailDialogVisible = false">关闭</el-button>
          <el-button type="primary" @click="editFromDetail">
            <el-icon><Edit /></el-icon>编辑信息
          </el-button>
          <el-button type="danger" plain @click="deleteFromDetail">
            <el-icon><Delete /></el-icon>删除员工
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 批量操作对话框 -->
    <el-dialog v-model="batchDialogVisible" title="批量设置考勤" width="450px">
      <el-form label-width="100px">
        <el-form-item label="选择员工"
          ><div class="batch-employees">
            <el-tag
              v-for="emp in batchEmployees"
              :key="emp.id"
              size="small"
              style="margin: 2px"
              >{{ emp.name }}</el-tag
            >
          </div></el-form-item
        >
        <el-form-item label="选择日期" required
          ><el-date-picker
            v-model="batchDate"
            type="date"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
        /></el-form-item>
        <el-form-item label="考勤状态" required>
          <el-radio-group v-model="batchStatus"
            ><el-radio value="work"
              ><span class="work-option">✅ 出勤</span></el-radio
            ><el-radio value="rest_half"
              ><span class="rest-half-option">🌙 休假半天</span></el-radio
            ><el-radio value="rest_full"
              ><span class="rest-full-option">🌙🌙 休假一天</span></el-radio
            ><el-radio value="leave"
              ><span class="leave-option">📝 请假半天</span></el-radio
            ><el-radio value="off_post"
              ><span class="off-post-option">📝📝 请假一天</span></el-radio
            ><el-radio value="absent"
              ><span class="absent-option">❌ 旷工</span></el-radio
            ><el-radio value="resigned"
              ><span class="resigned-option">📄 离职</span></el-radio
            ></el-radio-group
          >
        </el-form-item>
      </el-form>
      <template #footer
        ><el-button @click="batchDialogVisible = false">取消</el-button
        ><el-button
          type="primary"
          @click="confirmBatchSet"
          :loading="batchSetting"
          >确定</el-button
        ></template
      >
    </el-dialog>

    <!-- 添加绩效分对话框 -->
    <el-dialog v-model="scoreDialogVisible" title="添加绩效分" width="500px">
      <el-form
        :model="scoreForm"
        :rules="scoreRules"
        ref="scoreFormRef"
        label-width="100px"
      >
        <el-form-item label="选择员工" prop="employee_id">
          <el-select
            v-model="scoreForm.employee_id"
            placeholder="选择员工"
            filterable
            style="width: 100%"
            @change="onScoreEmployeeChange"
          >
            <el-option
              v-for="emp in employees"
              :key="emp.id"
              :label="`${emp.name} (${emp.position || '-'})`"
              :value="emp.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="员工岗位"
          ><span class="info-text">{{
            scoreForm.position || "-"
          }}</span></el-form-item
        >
        <el-form-item label="当前分数"
          ><span class="info-text"
            >{{ scoreForm.current_score }}分</span
          ></el-form-item
        >
        <el-form-item label="加减分数" prop="score"
          ><el-input-number
            v-model="scoreForm.score"
            :min="-50"
            :max="50"
            :step="1"
            placeholder="正数为加分，负数为扣分"
            style="width: 100%"
          /><span class="help-text"
            >正数表示加分，负数表示扣分</span
          ></el-form-item
        >
        <el-form-item label="结余分数"
          ><span class="info-text highlight"
            >{{ scoreForm.current_score + (scoreForm.score || 0) }}分</span
          ></el-form-item
        >
        <el-form-item label="原因" prop="reason"
          ><el-input
            v-model="scoreForm.reason"
            type="textarea"
            :rows="3"
            placeholder="请输入加减分原因"
        /></el-form-item>
        <el-form-item label="日期" prop="date"
          ><el-date-picker
            v-model="scoreForm.date"
            type="date"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
        /></el-form-item>
      </el-form>
      <template #footer
        ><el-button @click="scoreDialogVisible = false">取消</el-button
        ><el-button
          type="primary"
          @click="confirmAddScore"
          :loading="scoreSubmitting"
          >确定</el-button
        ></template
      >
    </el-dialog>

    <!-- 添加罚款对话框 -->
    <el-dialog
      v-model="penaltyDialogVisible"
      title="添加罚款记录"
      width="500px"
    >
      <el-form
        :model="penaltyForm"
        :rules="penaltyRules"
        ref="penaltyFormRef"
        label-width="100px"
      >
        <el-form-item label="员工" prop="employee_id"
          ><el-select
            v-model="penaltyForm.employee_id"
            placeholder="选择员工"
            filterable
            style="width: 100%"
            ><el-option
              v-for="emp in employees"
              :key="emp.id"
              :label="`${emp.name} (${emp.position || '-'})`"
              :value="emp.id" /></el-select
        ></el-form-item>
        <el-form-item label="罚款日期" prop="penalty_date"
          ><el-date-picker
            v-model="penaltyForm.penalty_date"
            type="date"
            placeholder="选择罚款日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
        /></el-form-item>
        <el-form-item label="罚款金额" prop="amount"
          ><el-input-number
            v-model="penaltyForm.amount"
            :min="0"
            :step="10"
            style="width: 100%"
        /></el-form-item>
        <el-form-item label="罚款类型" prop="category"
          ><el-select
            v-model="penaltyForm.category"
            filterable
            allow-create
            default-first-option
            placeholder="请选择或输入罚款类型"
            style="width: 100%"
            ><el-option label="迟到" value="迟到" /><el-option
              label="早退"
              value="早退" /><el-option label="旷工" value="旷工" /><el-option
              label="小厕超时"
              value="大厕超时" /><el-option
              label="吃饭超时"
              value="抽烟或休息超时" /><el-option
              label="其他"
              value="其他" /></el-select
        ></el-form-item>
        <el-form-item label="罚款原因" prop="reason"
          ><el-input
            v-model="penaltyForm.reason"
            type="textarea"
            :rows="3"
            placeholder="请输入罚款原因"
        /></el-form-item>
      </el-form>
      <template #footer
        ><el-button @click="penaltyDialogVisible = false">取消</el-button
        ><el-button
          type="primary"
          @click="submitPenalty"
          :loading="submittingPenalty"
          >确定</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Check,
  Download,
  Plus,
  Edit,
  Delete,
  Calendar,
  User,
  DataLine,
  Search,
  Select,
  ArrowRight,
  TrendCharts,
  Warning,
  Money,
  Document,
} from "@element-plus/icons-vue";
import { attendanceApi } from "./admin_api";
import { Refresh } from "@element-plus/icons-vue";

// ==================== 状态变量 ====================
const activeTab = ref("attendance");
const loading = ref(false);
const saving = ref(false);
const submittingEmployee = ref(false);
const batchSetting = ref(false);
const savingPerformance = ref(false);
const submittingPenalty = ref(false);
const scoreSubmitting = ref(false);

const employees = ref([]);
const attendanceData = ref({});
const selectedEmployees = ref([]);

const filters = ref({ yearMonth: getCurrentYearMonth(), searchKeyword: "" });

// 考勤汇总统计
const summaryStats = computed(() => {
  // ✅ 使用总员工数（来自分页组件的 total）
  const totalEmps = employeeTotal.value; // 改为这个

  if (totalEmps === 0 || actualDays.value.length === 0) {
    return {
      totalEmployees: 0,
      totalWorkDays: 0,
      totalLeaveRestDays: 0,
      avgAttendanceRate: 0,
    };
  }

  let totalWork = 0;
  let totalLeaveRest = 0;

  // 统计当前页员工的考勤数据（用于计算出勤率）
  for (const emp of filteredEmployees.value) {
    totalWork += getWorkDays(emp);
    totalLeaveRest += getLeaveRestDays(emp);
  }

  const totalPossibleWorkDays = totalEmps * actualDays.value.length;
  const attendanceRate =
    totalPossibleWorkDays > 0
      ? Math.round((totalWork / totalPossibleWorkDays) * 100)
      : 0;

  return {
    totalEmployees: totalEmps, // ✅ 显示总员工数 40
    totalWorkDays: totalWork, // 当前页员工的总出勤天数
    totalLeaveRestDays: totalLeaveRest, // 当前页员工的请假/休假天数
    avgAttendanceRate: attendanceRate, // 基于总员工数计算的出勤率
  };
});

// 绩效考核相关
const performanceMonth = ref(getCurrentYearMonth());
const performanceSearch = ref("");
const performanceData = ref([]);
const scoreDialogVisible = ref(false);
const scoreFormRef = ref(null);
const employeePage = ref(1);
const employeePageSize = ref(100);
const employeeTotal = ref(0);
const scoreForm = ref({
  employee_id: "",
  position: "",
  current_score: 10,
  score: 0,
  reason: "",
  date: getToday(),
});
const scoreRules = {
  employee_id: [{ required: true, message: "请选择员工", trigger: "change" }],
  score: [{ required: true, message: "请输入加减分数", trigger: "blur" }],
  reason: [{ required: true, message: "请输入原因", trigger: "blur" }],
  date: [{ required: true, message: "请选择日期", trigger: "change" }],
};

// 罚款相关
const penaltyMonth = ref(getCurrentYearMonth());
const penaltySearchEmployee = ref("");
const penaltyRecords = ref([]);
const penaltyTotal = ref(0);
const penaltyPage = ref(1);
const penaltyPageSize = ref(20);
const penaltyStats = ref({
  totalAmount: 0,
  employeeCount: 0,
  recordCount: 0,
  avgAmount: 0,
});
const penaltyDialogVisible = ref(false);
const penaltyFormRef = ref(null);
const penaltyForm = ref({
  employee_id: "",
  penalty_date: "",
  amount: 0,
  category: "迟到",
  reason: "",
});
const penaltyRules = {
  employee_id: [{ required: true, message: "请选择员工", trigger: "change" }],
  penalty_date: [
    { required: true, message: "请选择罚款日期", trigger: "change" },
  ],
  amount: [{ required: true, message: "请输入罚款金额", trigger: "blur" }],
  reason: [{ required: true, message: "请输入罚款原因", trigger: "blur" }],
};

// 批量操作
const batchDialogVisible = ref(false);
const batchDate = ref("");
const batchStatus = ref("work");
const batchEmployees = ref([]);

// 员工详情
const detailDialogVisible = ref(false);
const currentEmployee = ref(null);

// 员工对话框
const employeeDialogVisible = ref(false);
const employeeDialogTitle = ref("添加员工");
const employeeFormRef = ref(null);
const employeeForm = ref({
  id: null,
  name: "",
  employee_id: "",
  position: "",
  hire_date: "",
  work_location: "现场",
});
const employeeRules = {
  name: [{ required: true, message: "请输入姓名", trigger: "blur" }],
  employee_id: [{ required: true, message: "请输入员工ID", trigger: "blur" }],
  hire_date: [{ required: true, message: "请选择入职日期", trigger: "change" }],
};

const dayWidth = "85px";

const actualDays = computed(() => {
  if (!filters.value.yearMonth)
    return Array.from({ length: 31 }, (_, i) => i + 1);
  const [year, month] = filters.value.yearMonth.split("-");
  const lastDay = new Date(parseInt(year), parseInt(month), 0).getDate();
  return Array.from({ length: lastDay }, (_, i) => i + 1);
});

const filteredEmployees = computed(() => {
  if (!filters.value.searchKeyword) return employees.value;
  const keyword = filters.value.searchKeyword.toLowerCase();
  return employees.value.filter((e) => e.name.toLowerCase().includes(keyword));
});

const filteredPerformanceData = computed(() => {
  if (!performanceSearch.value) return performanceData.value;
  const keyword = performanceSearch.value.toLowerCase();
  return performanceData.value.filter((p) =>
    p.employee_name?.toLowerCase().includes(keyword),
  );
});

const filteredPenaltyRecords = computed(() => {
  if (!penaltySearchEmployee.value) return penaltyRecords.value;
  const keyword = penaltySearchEmployee.value.toLowerCase();
  return penaltyRecords.value.filter((r) =>
    r.employee_name?.toLowerCase().includes(keyword),
  );
});

const isAllSelected = computed(
  () =>
    filteredEmployees.value.length > 0 &&
    selectedEmployees.value.length === filteredEmployees.value.length,
);
const isIndeterminate = computed(
  () =>
    selectedEmployees.value.length > 0 &&
    selectedEmployees.value.length < filteredEmployees.value.length,
);

// 单个考勤状态对话框
const statusDialogVisible = ref(false);
const statusChanging = ref(false);
const currentStatusEmployee = ref(null);
const currentStatusDate = ref("");
const currentStatusDay = ref(null);
const tempStatus = ref("work");

// 打开状态选择对话框
const openStatusDialog = (employee, day) => {
  // 阻止事件冒泡，避免触发行点击
  event?.stopPropagation();

  currentStatusEmployee.value = employee;
  currentStatusDate.value = `${filters.value.yearMonth}-${String(day).padStart(2, "0")}`;
  currentStatusDay.value = day;
  tempStatus.value = getDayStatus(employee, day) || "work";
  statusDialogVisible.value = true;
};

// 确认修改状态
const confirmStatusChange = async () => {
  statusChanging.value = true;
  try {
    updateDayStatus(
      currentStatusEmployee.value,
      currentStatusDay.value,
      tempStatus.value,
    );

    // 如果自动保存关闭，显示提示
    if (!autoSaveEnabled.value) {
      ElMessage.success("考勤状态已更新（请记得手动保存）");
    } else {
      // 自动保存会在防抖后自动执行
      ElMessage.success("考勤状态已更新，将自动保存");
    }

    statusDialogVisible.value = false;
  } catch (error) {
    ElMessage.error("更新失败");
  } finally {
    statusChanging.value = false;
  }
};
// 重置表单
const resetStatusForm = () => {
  currentStatusEmployee.value = null;
  currentStatusDate.value = "";
  currentStatusDay.value = null;
  tempStatus.value = "work";
};

// ==================== 工具函数 ====================
function getCurrentYearMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function getToday() {
  return new Date().toISOString().split("T")[0];
}

const getAttendanceRateType = (rate) => {
  if (rate >= 90) return "success";
  if (rate >= 70) return "warning";
  return "danger";
};

function formatDate(date) {
  if (!date) return "-";
  const str = String(date);
  if (str.includes("-")) return str.substring(0, 10);
  const d = new Date(date);
  if (isNaN(d.getTime())) return "-";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function isWeekend(day) {
  const [year, month] = filters.value.yearMonth.split("-");
  const date = new Date(parseInt(year), parseInt(month) - 1, day);
  const dayOfWeek = date.getDay();
  return dayOfWeek === 0 || dayOfWeek === 6;
}

const getDayStatus = (employee, day) => {
  const dateKey = `${filters.value.yearMonth}-${String(day).padStart(2, "0")}`;
  const empKey = String(employee.id); // ✅ 统一使用字符串
  return attendanceData.value[empKey]?.[dateKey]?.status || "";
};

const updateDayStatus = (employee, day, status) => {
  const dateKey = `${filters.value.yearMonth}-${String(day).padStart(2, "0")}`;
  const empKey = String(employee.id);
  if (!attendanceData.value[empKey]) {
    attendanceData.value[empKey] = {};
  }
  if (!attendanceData.value[empKey][dateKey]) {
    attendanceData.value[empKey][dateKey] = {};
  }
  attendanceData.value[empKey][dateKey].status = status;

  // ✅ 触发自动保存
  triggerAutoSave(employee.id);
};

function getStatusClass(status) {
  const map = {
    work: "status-work",
    rest_half: "status-rest-half",
    rest_full: "status-rest-full",
    leave: "status-leave",
    absent: "status-absent",
    off_post: "status-off-post",
    resigned: "status-resigned",
  };
  return map[status] || "";
}

const getWorkDays = (employee) => {
  if (!employee) return 0;
  const empKey = String(employee.id); // ✅ 统一使用字符串
  const records = attendanceData.value[empKey] || {};
  let count = 0;
  for (const [, value] of Object.entries(records)) {
    if (value.status === "work") {
      count += 1;
    } else if (value.status === "rest_half" || value.status === "leave") {
      count += 0.5;
    }
  }
  return count;
};

const getLeaveRestDays = (employee) => {
  if (!employee) return 0;
  const empKey = String(employee.id); // ✅ 统一使用字符串
  const records = attendanceData.value[empKey] || {};
  let count = 0;
  for (const [, value] of Object.entries(records)) {
    if (value.status === "rest_half") count += 0.5;
    else if (value.status === "rest_full") count += 1;
    else if (value.status === "leave") count += 0.5;
    else if (value.status === "off_post") count += 1;
  }
  return count;
};

const refreshing = ref(false);
const refreshAttendanceData = async () => {
  refreshing.value = true;
  try {
    await loadEmployees();
    if (filters.value.yearMonth) {
      await loadAttendanceData();
    }
    ElMessage.success("数据已刷新");
  } catch (error) {
    console.error("刷新失败:", error);
    ElMessage.error("刷新失败");
  } finally {
    refreshing.value = false;
  }
};

// 获取状态显示文本
const getStatusText = (status) => {
  const map = {
    work: "出勤",
    rest_half: "半休",
    rest_full: "全休",
    leave: "半假",
    absent: "旷工",
    off_post: "全假",
    resigned: "离职",
    "": "-",
  };
  return map[status] || "-";
};

// ==================== 批量选择 ====================
function toggleSelectAll() {
  if (isAllSelected.value) selectedEmployees.value = [];
  else selectedEmployees.value = filteredEmployees.value.map((e) => e.id);
}

function toggleSelectEmployee(id) {
  const index = selectedEmployees.value.indexOf(id);
  if (index === -1) selectedEmployees.value.push(id);
  else selectedEmployees.value.splice(index, 1);
}

// ==================== 批量操作 ====================
function openBatchDialog() {
  if (selectedEmployees.value.length === 0) return;
  batchEmployees.value = employees.value.filter((e) =>
    selectedEmployees.value.includes(e.id),
  );
  batchDate.value = "";
  batchStatus.value = "work";
  batchDialogVisible.value = true;
}

const confirmBatchSet = async () => {
  if (!batchDate.value) {
    ElMessage.warning("请选择日期");
    return;
  }
  batchSetting.value = true;
  try {
    const affectedEmployees = [];

    for (const emp of batchEmployees.value) {
      const day = parseInt(batchDate.value.split("-")[2]);
      updateDayStatus(emp, day, batchStatus.value);
      affectedEmployees.push(emp);
    }

    // 如果自动保存开启，立即保存（批量操作不延迟）
    if (autoSaveEnabled.value) {
      await saveMultipleEmployeesAttendance(affectedEmployees, true);
    } else {
      ElMessage.success(
        `已为 ${batchEmployees.value.length} 名员工设置 ${batchDate.value} 的考勤（请记得手动保存）`,
      );
    }

    batchDialogVisible.value = false;
  } catch (error) {
    ElMessage.error("操作失败");
  } finally {
    batchSetting.value = false;
  }
};

// ==================== 自动保存相关 ====================
const autoSaveEnabled = ref(true); // 自动保存开关
const pendingSaves = ref(new Set()); // 待保存的员工ID集合
let autoSaveTimer = null;

// 自动保存延迟时间（毫秒）
const AUTO_SAVE_DELAY = 1500;

// 处理自动保存开关变化
const handleAutoSaveToggle = (value) => {
  if (value) {
    ElMessage.success("自动保存已开启，修改后将自动保存");
  } else {
    ElMessage.info("自动保存已关闭，请记得手动点击「保存全部」按钮");
  }
};

// 保存单个员工的考勤数据
const saveEmployeeAttendance = async (employee, showMessage = false) => {
  try {
    const empKey = String(employee.id);
    const empRecords = attendanceData.value[empKey] || {};

    // 只保存有数据的记录
    const recordsToSave = {};
    for (const [date, record] of Object.entries(empRecords)) {
      if (record.status && record.status !== "") {
        recordsToSave[date] = record;
      }
    }

    if (Object.keys(recordsToSave).length === 0) {
      return { success: true, saved: false };
    }

    const saveData = {
      [empKey]: recordsToSave,
    };

    await attendanceApi.saveRecords({
      year_month: filters.value.yearMonth,
      data: saveData,
    });

    if (showMessage) {
      ElMessage.success(`${employee.name} 的考勤已保存`);
    }

    return { success: true, saved: true };
  } catch (error) {
    console.error("保存员工考勤失败:", error);
    if (showMessage) {
      ElMessage.error(`保存 ${employee.name} 失败: ${error.message}`);
    }
    throw error;
  }
};

// 批量保存多个员工的考勤数据
const saveMultipleEmployeesAttendance = async (
  employees,
  showMessage = false,
) => {
  try {
    const saveData = {};

    for (const employee of employees) {
      const empKey = String(employee.id);
      const empRecords = attendanceData.value[empKey] || {};

      const recordsToSave = {};
      for (const [date, record] of Object.entries(empRecords)) {
        if (record.status && record.status !== "") {
          recordsToSave[date] = record;
        }
      }

      if (Object.keys(recordsToSave).length > 0) {
        saveData[empKey] = recordsToSave;
      }
    }

    if (Object.keys(saveData).length === 0) {
      return { success: true, savedCount: 0 };
    }

    await attendanceApi.saveRecords({
      year_month: filters.value.yearMonth,
      data: saveData,
    });

    if (showMessage) {
      ElMessage.success(
        `已保存 ${Object.keys(saveData).length} 名员工的考勤数据`,
      );
    }

    return { success: true, savedCount: Object.keys(saveData).length };
  } catch (error) {
    console.error("批量保存失败:", error);
    if (showMessage) {
      ElMessage.error(`保存失败: ${error.message}`);
    }
    throw error;
  }
};

// 触发自动保存（带防抖）
const triggerAutoSave = (employeeId) => {
  if (!autoSaveEnabled.value) return;

  // 添加到待保存集合
  pendingSaves.value.add(employeeId);

  // 清除之前的定时器
  if (autoSaveTimer) {
    clearTimeout(autoSaveTimer);
  }

  // 设置新的定时器
  autoSaveTimer = setTimeout(async () => {
    const employeesToSave = employees.value.filter((e) =>
      pendingSaves.value.has(e.id),
    );
    if (employeesToSave.length > 0) {
      try {
        await saveMultipleEmployeesAttendance(employeesToSave);
        console.log(`✅ 自动保存了 ${employeesToSave.length} 名员工的考勤数据`);
        pendingSaves.value.clear();
      } catch (error) {
        console.error("自动保存失败:", error);
      }
    }
  }, AUTO_SAVE_DELAY);
};

async function batchDeleteEmployees() {
  if (selectedEmployees.value.length === 0) return;
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedEmployees.value.length} 名员工吗？`,
      "警告",
      { type: "warning" },
    );
    for (const empId of selectedEmployees.value) {
      await attendanceApi.deleteEmployee(empId);
      delete attendanceData.value[empId];
    }
    employees.value = employees.value.filter(
      (e) => !selectedEmployees.value.includes(e.id),
    );
    selectedEmployees.value = [];
    ElMessage.success("删除成功");
    loadPerformanceData();
    loadPenaltyData();
  } catch (error) {
    if (error !== "cancel") ElMessage.error("删除失败");
  }
}

// ===== 新增：当前员工的绩效和罚款数据 =====
const currentPerformance = ref(null);
const currentPenaltyTotal = ref(0);
const currentPenaltyRecords = ref([]);

// 获取当前员工的绩效数据
const loadCurrentEmployeePerformance = async (employeeId) => {
  try {
    const token = localStorage.getItem("token");
    const response = await fetch(
      `/api/attendance/performance?month=${filters.value.yearMonth}&employee_id=${employeeId}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      },
    );
    const data = await response.json();

    if (data.items && data.items.length > 0) {
      currentPerformance.value = data.items[0];
    } else {
      currentPerformance.value = {
        employee_id: employeeId,
        total_score: 10,
        grade: "合格",
        score_records: [],
      };
    }
  } catch (error) {
    console.error("加载绩效失败:", error);
    currentPerformance.value = {
      employee_id: employeeId,
      total_score: 10,
      grade: "合格",
      score_records: [],
    };
  }
};

// 获取当前员工的罚款数据
const loadCurrentEmployeePenalty = async (employeeId) => {
  try {
    const token = localStorage.getItem("token");
    const response = await fetch(
      `/api/attendance/penalty/records?month=${filters.value.yearMonth}&employee_id=${employeeId}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      },
    );
    const data = await response.json();

    currentPenaltyRecords.value = data.items || [];
    currentPenaltyTotal.value = currentPenaltyRecords.value.reduce(
      (sum, r) => sum + r.amount,
      0,
    );
  } catch (error) {
    console.error("加载罚款失败:", error);
    currentPenaltyRecords.value = [];
    currentPenaltyTotal.value = 0;
  }
};

// ==================== 员工详情 ====================
const showEmployeeDetail = async (employee) => {
  currentEmployee.value = employee;

  // 加载绩效数据
  await loadCurrentEmployeePerformance(employee.id);
  // 加载罚款数据
  await loadCurrentEmployeePenalty(employee.id);

  detailDialogVisible.value = true;
};
// 从详情页添加加减分
const showScoreDialogFromDetail = () => {
  showAddScoreDialogForEmployee({
    employee_id: currentEmployee.value.id,
    employee_name: currentEmployee.value.name,
    position: currentEmployee.value.position,
    total_score: currentPerformance.value?.total_score || 10,
    score_records: currentPerformance.value?.score_records || [],
  });
};
// 从详情页添加罚款
const showPenaltyDialogFromDetail = () => {
  // 打开罚款对话框并预填员工
  penaltyForm.value = {
    employee_id: currentEmployee.value.id,
    penalty_date: getToday(),
    amount: 0,
    category: "迟到",
    reason: "",
  };
  penaltyDialogVisible.value = true;
};
// 查看所有加减分记录
const viewAllScoreRecords = () => {
  detailDialogVisible.value = false;
  // 这里可以打开一个完整的记录对话框或切换到绩效标签页
  activeTab.value = "performance";
  performanceSearch.value = currentEmployee.value.name;
};
// 查看所有罚款记录
const viewAllPenaltyRecords = () => {
  detailDialogVisible.value = false;
  // 切换到罚款标签页并筛选
  activeTab.value = "penalty";
  penaltySearchEmployee.value = currentEmployee.value.name;
};
async function showEmployeeDetailFromPerformance(row) {
  currentEmployee.value = employees.value.find((e) => e.id === row.employee_id);
  if (currentEmployee.value) {
    await loadCurrentEmployeePerformance(currentEmployee.value.id);
    await loadCurrentEmployeePenalty(currentEmployee.value.id);
  }
  detailDialogVisible.value = true;
}

async function showEmployeeDetailFromPenalty(row) {
  currentEmployee.value = employees.value.find((e) => e.id === row.employee_id);
  if (currentEmployee.value) {
    await loadCurrentEmployeePerformance(currentEmployee.value.id);
    await loadCurrentEmployeePenalty(currentEmployee.value.id);
  }
  detailDialogVisible.value = true;
}
function editFromDetail() {
  editEmployee(currentEmployee.value);
}
async function deleteFromDetail() {
  detailDialogVisible.value = false;
  await deleteEmployee(currentEmployee.value);
}

// ==================== 数据加载 ====================
const loadEmployees = async () => {
  try {
    const response = await attendanceApi.getEmployees({
      skip: (employeePage.value - 1) * employeePageSize.value,
      limit: employeePageSize.value,
      search: filters.value.searchKeyword,
    });
    employees.value = response.items || [];
    employeeTotal.value = response.total || 0;

    if (employees.value.length === 0 && employeeTotal.value === 0) {
      ElMessage.info("暂无员工数据，请点击「添加员工」按钮添加");
    }

    return Promise.resolve(); // 返回 Promise，支持 await
  } catch (error) {
    console.error("加载员工失败:", error);
    employees.value = [];
    employeeTotal.value = 0;
    ElMessage.error(
      "加载员工列表失败: " + (error.response?.data?.detail || error.message),
    );
    return Promise.reject(error);
  }
};

// 分页处理函数
const handleEmployeeSizeChange = async (val) => {
  employeePageSize.value = val;
  employeePage.value = 1;
  await loadEmployees(); // 等待员工加载完成
  if (filters.value.yearMonth) {
    await loadAttendanceData(); // 然后加载考勤数据
  }
};

const handleEmployeeCurrentChange = async (val) => {
  employeePage.value = val;
  await loadEmployees(); // 等待员工加载完成
  if (filters.value.yearMonth) {
    await loadAttendanceData(); // 然后加载考勤数据
  }
};

const loadAttendanceData = async () => {
  if (!filters.value.yearMonth) {
    ElMessage.warning("请选择月份");
    return;
  }

  // 如果没有员工，直接返回
  if (employees.value.length === 0) {
    attendanceData.value = {};
    return;
  }

  loading.value = true;
  try {
    // 获取当前页所有员工的ID
    const employeeIds = employees.value.map((emp) => emp.id);

    console.log(
      `📊 加载考勤数据: 月份=${filters.value.yearMonth}, 员工数=${employeeIds.length}`,
    );

    // ✅ 使用批量接口，一次请求获取所有员工的考勤数据
    const response = await attendanceApi.getRecordsByEmployees(
      filters.value.yearMonth,
      employeeIds,
    );

    const rawData = response.data || {};

    // 规范化数据格式
    const normalizedData = {};
    for (const [empId, records] of Object.entries(rawData)) {
      normalizedData[String(empId)] = records;
    }

    attendanceData.value = normalizedData;

    // 确保当前页每个员工都有数据对象
    for (const emp of employees.value) {
      const empKey = String(emp.id);
      if (!attendanceData.value[empKey]) {
        attendanceData.value[empKey] = {};
      }
    }

    console.log(
      `✅ 考勤数据加载完成: ${Object.keys(attendanceData.value).length} 名员工`,
    );
  } catch (error) {
    console.error("加载考勤数据失败:", error);
    // 初始化空数据
    for (const emp of employees.value) {
      attendanceData.value[String(emp.id)] = {};
    }
  } finally {
    loading.value = false;
  }
};

const saveAllAttendance = async () => {
  saving.value = true;
  try {
    const saveData = {};
    for (const emp of employees.value) {
      // ✅ 确保使用数字ID的字符串形式
      const empKey = String(emp.id);
      const empRecords = attendanceData.value[emp.id] || {};

      // 只保存有数据的记录
      const recordsToSave = {};
      for (const [date, record] of Object.entries(empRecords)) {
        if (record.status && record.status !== "") {
          recordsToSave[date] = record;
        }
      }

      if (Object.keys(recordsToSave).length > 0) {
        saveData[empKey] = recordsToSave;
      }
    }

    if (Object.keys(saveData).length === 0) {
      ElMessage.warning("没有数据需要保存");
      return;
    }

    const response = await attendanceApi.saveRecords({
      year_month: filters.value.yearMonth,
      data: saveData,
    });

    ElMessage.success(
      `考勤数据已保存 (${Object.keys(saveData).length} 名员工)`,
    );
  } catch (error) {
    console.error("保存失败:", error);
    ElMessage.error(error.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
};

async function updateEmployeeField(employee, field, value) {
  employee[field] = value;
  try {
    await attendanceApi.updateEmployee(employee.id, { [field]: value });
    ElMessage.success("更新成功");
  } catch (error) {
    console.error("更新失败:", error);
  }
}

// ==================== 员工管理 ====================
function showAddEmployeeDialog() {
  employeeDialogTitle.value = "添加员工";
  employeeForm.value = {
    id: null,
    name: "",
    employee_id: "",
    position: "",
    hire_date: "",
    work_location: "现场",
  };
  employeeDialogVisible.value = true;
}

function editEmployee(row) {
  employeeDialogTitle.value = "编辑员工";
  employeeForm.value = { ...row };
  employeeDialogVisible.value = true;
}

async function deleteEmployee(row) {
  try {
    await ElMessageBox.confirm(`确定要删除员工 "${row.name}" 吗？`, "警告", {
      type: "warning",
    });
    await attendanceApi.deleteEmployee(row.id);
    employees.value = employees.value.filter((e) => e.id !== row.id);
    delete attendanceData.value[row.id];
    selectedEmployees.value = selectedEmployees.value.filter(
      (id) => id !== row.id,
    );
    ElMessage.success("删除成功");
    loadPerformanceData();
    loadPenaltyData();
  } catch (error) {
    if (error !== "cancel") ElMessage.error("删除失败");
  }
}

async function submitEmployee() {
  if (!employeeFormRef.value) return;
  await employeeFormRef.value.validate(async (valid) => {
    if (valid) {
      submittingEmployee.value = true;
      try {
        console.log("提交的员工数据:", employeeForm.value);

        if (employeeForm.value.id) {
          // 编辑员工
          const updateData = {
            name: employeeForm.value.name,
            employee_id: employeeForm.value.employee_id,
            position: employeeForm.value.position,
            hire_date: employeeForm.value.hire_date,
            work_location: employeeForm.value.work_location,
          };
          console.log("更新数据:", updateData);

          await attendanceApi.updateEmployee(employeeForm.value.id, updateData);
          ElMessage.success("员工信息已更新");

          // 更新本地数组
          const index = employees.value.findIndex(
            (e) => e.id === employeeForm.value.id,
          );
          if (index !== -1) {
            employees.value[index] = {
              ...employees.value[index],
              ...updateData,
            };
          }

          // ✅ 新增：刷新详情页数据（如果详情页是打开的）
          if (detailDialogVisible.value && currentEmployee.value) {
            // 更新当前员工信息
            currentEmployee.value = {
              ...currentEmployee.value,
              ...updateData,
            };
            // 刷新绩效和罚款数据
            await loadCurrentEmployeePerformance(currentEmployee.value.id);
            await loadCurrentEmployeePenalty(currentEmployee.value.id);
          }
        } else {
          // 添加员工
          const createData = {
            name: employeeForm.value.name,
            employee_id: employeeForm.value.employee_id,
            position: employeeForm.value.position,
            hire_date: employeeForm.value.hire_date,
            work_location: employeeForm.value.work_location,
          };
          console.log("创建数据:", createData);

          const response = await attendanceApi.createEmployee(createData);
          console.log("创建响应:", response);

          employees.value.push(response);
          attendanceData.value[response.id] = {};
          ElMessage.success("员工已添加");
        }

        employeeDialogVisible.value = false;
        await loadAttendanceData();
        await loadPerformanceData();
      } catch (error) {
        console.error("操作失败:", error);
        ElMessage.error(error.response?.data?.detail || "操作失败");
      } finally {
        submittingEmployee.value = false;
      }
    }
  });
}

let searchTimer;
function handleSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    selectedEmployees.value = [];
    employeePage.value = 1;
    await loadEmployees(); // 等待员工加载完成
    if (filters.value.yearMonth) {
      await loadAttendanceData(); // 然后加载考勤数据
    }
  }, 300);
}

const handleMonthChange = async () => {
  employeePage.value = 1; // 重置到第一页
  await loadEmployees(); // 重新加载员工
  await loadAttendanceData(); // 重新加载考勤数据
};

// 监听筛选员工变化，更新汇总
watch(filteredEmployees, () => {}, { deep: true });

// ==================== 导出功能 ====================
function exportAttendanceTable() {
  if (!employees.value.length || !filters.value.yearMonth) {
    ElMessage.warning("没有数据可导出");
    return;
  }
  const headers = [
    "入职日期",
    "姓名",
    "岗位",
    "办公地点",
    "实际上班",
    "请假/休假天数",
    ...actualDays.value,
  ];
  const rows = employees.value.map((emp) => {
    const row = [
      emp.hire_date || "",
      emp.name,
      emp.position || "-",
      emp.work_location,
      getWorkDays(emp),
      getLeaveRestDays(emp),
    ];
    for (let day of actualDays.value) {
      const status = getDayStatus(emp, day);
      const map = {
        work: "出勤",
        rest_half: "半休",
        rest_full: "全休",
        leave: "半假",
        absent: "旷工",
        off_post: "全假",
        resigned: "离职",
      };
      row.push(map[status] || "");
    }
    return row;
  });
  const csvContent = [
    headers.join(","),
    ...rows.map((row) => row.map((cell) => `"${cell}"`).join(",")),
  ].join("\n");
  const blob = new Blob(["\uFEFF" + csvContent], {
    type: "text/csv;charset=utf-8;",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `考勤表_${filters.value.yearMonth}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

// ==================== 绩效考核功能 ====================
async function loadPerformanceData() {
  try {
    // ✅ 直接使用 fetch，不通过 attendanceApi
    const token = localStorage.getItem("token");
    const response = await fetch(
      `/api/attendance/performance?month=${performanceMonth.value}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      },
    );
    const data = await response.json();

    if (data.items && data.items.length > 0) {
      performanceData.value = data.items.map((item) => {
        let scoreRecords = item.score_records || [];
        if (typeof scoreRecords === "string") {
          try {
            scoreRecords = JSON.parse(scoreRecords);
          } catch (e) {
            console.error("解析 score_records 失败:", e);
            scoreRecords = [];
          }
        }

        // 计算总分
        let total = 10;
        for (const record of scoreRecords) {
          total += record.score;
        }

        // ✅ 根据新规则计算评级
        let grade = "";
        if (total >= 9) {
          grade = "优秀";
        } else if (total >= 5) {
          grade = "合格";
        } else {
          grade = "待提升";
        }

        return {
          employee_id: item.employee_id,
          employee_name: item.employee_name,
          position: item.position || "-",
          base_score: 10,
          score_records: scoreRecords,
          total_score: total, // ✅ 使用重新计算的总分
          grade: grade, // ✅ 使用新规则计算的评级
        };
      });

      performanceData.value = [...performanceData.value];
    } else {
      generateDefaultPerformanceData();
    }
  } catch (error) {
    console.error("加载绩效考核失败:", error);
    generateDefaultPerformanceData();
  }
}

function generateDefaultPerformanceData() {
  // 基于所有员工生成绩效考核数据
  performanceData.value = employees.value.map((emp) => ({
    employee_id: emp.id,
    employee_name: emp.name,
    position: emp.position || "-",
    base_score: 10,
    score_records: [],
    total_score: 10,
    grade: "满分",
  }));
}

function calculateTotalScore(employee) {
  let total = 10;
  if (employee.score_records) {
    for (const record of employee.score_records) {
      total += record.score;
    }
  }
  employee.total_score = total;
  if (employee.total_score >= 9) employee.grade = "优秀";
  else if (employee.total_score >= 7) employee.grade = "良好";
  else if (employee.total_score >= 5) employee.grade = "合格";
  else employee.grade = "待提升";
  return total;
}

const getScoreType = (score) => {
  if (score >= 9) return "success";
  if (score >= 7) return "primary";
  if (score >= 5) return "warning";
  return "danger";
};

function getGradeType(grade) {
  const map = {
    优秀: "success",
    良好: "primary",
    合格: "warning",
    待提升: "danger",
  };
  return map[grade] || "info";
}
const hasPermission = (permission) => {
  // 可以根据实际权限系统实现
  return true; // 临时返回true，实际应该从userStore获取
};

function showAddScoreDialog() {
  scoreForm.value = {
    employee_id: "",
    position: "",
    current_score: 10,
    score: 0,
    reason: "",
    date: getToday(),
  };
  scoreDialogVisible.value = true;
}

function showAddScoreDialogForEmployee(row) {
  scoreForm.value = {
    employee_id: row.employee_id,
    position: row.position,
    current_score: row.total_score,
    score: 0,
    reason: "",
    date: getToday(),
  };
  scoreDialogVisible.value = true;
}

function onScoreEmployeeChange(employeeId) {
  const emp = employees.value.find((e) => e.id === employeeId);
  if (emp) {
    scoreForm.value.position = emp.position || "-";
    const perf = performanceData.value.find(
      (p) => p.employee_id === employeeId,
    );
    scoreForm.value.current_score = perf ? perf.total_score : 10;
  }
}

async function confirmAddScore() {
  if (!scoreFormRef.value) return;
  await scoreFormRef.value.validate(async (valid) => {
    if (valid) {
      scoreSubmitting.value = true;
      try {
        let perf = performanceData.value.find(
          (p) => p.employee_id === scoreForm.value.employee_id,
        );
        if (!perf) {
          const emp = employees.value.find(
            (e) => e.id === scoreForm.value.employee_id,
          );
          perf = {
            employee_id: emp.id,
            employee_name: emp.name,
            position: emp.position || "-",
            base_score: 10,
            score_records: [],
            total_score: 10,
            grade: "合格",
          };
          performanceData.value.push(perf);
        }

        const newRecord = {
          date: scoreForm.value.date,
          score: scoreForm.value.score,
          reason: scoreForm.value.reason,
        };
        if (!perf.score_records) perf.score_records = [];
        perf.score_records.push(newRecord);
        calculateTotalScore(perf);

        await savePerformance();
        scoreDialogVisible.value = false;
        ElMessage.success("绩效分已添加");

        // ✅ 修复：先刷新数据，再打开详情页
        if (currentEmployee.value) {
          await loadCurrentEmployeePerformance(currentEmployee.value.id);
          await loadCurrentEmployeePenalty(currentEmployee.value.id);
          await loadPerformanceData();
          detailDialogVisible.value = true;
        }
      } catch (error) {
        ElMessage.error("操作失败");
      } finally {
        scoreSubmitting.value = false;
      }
    }
  });
}

async function deleteScoreRecord(row, index) {
  try {
    await ElMessageBox.confirm("确定要删除这条绩效记录吗？", "提示", {
      type: "warning",
    });
    row.score_records.splice(index, 1);
    calculateTotalScore(row);
    await savePerformance();
    ElMessage.success("删除成功");
  } catch (error) {
    if (error !== "cancel") ElMessage.error("删除失败");
  }
}

async function savePerformance() {
  savingPerformance.value = true;
  try {
    const token = localStorage.getItem("token");
    const itemsToSave = performanceData.value.map((item) => ({
      employee_id: item.employee_id,
      employee_name: item.employee_name,
      position: item.position,
      base_score: item.base_score || 10,
      score_records: item.score_records || [],
      total_score: item.total_score,
      grade: item.grade,
    }));

    const res = await fetch(`/api/attendance/performance/batch`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        month: performanceMonth.value,
        items: itemsToSave,
      }),
    });

    if (res.ok) {
      ElMessage.success("绩效考核已保存");
    } else {
      const error = await res.json();
      throw new Error(error.detail || "保存失败");
    }
  } catch (error) {
    console.error("保存失败:", error);
    ElMessage.error(error.message || "保存失败");
  } finally {
    savingPerformance.value = false;
  }
}

function exportPerformance() {
  if (!performanceData.value.length) {
    ElMessage.warning("没有数据可导出");
    return;
  }
  const headers = ["姓名", "岗位", "基础分", "绩效记录", "结余分数", "评级"];
  const rows = performanceData.value.map((p) => {
    const recordsStr = p.score_records
      .map(
        (r) =>
          `${r.date} ${r.score >= 0 ? `+${r.score}` : r.score}分 ${r.reason}`,
      )
      .join("; ");
    return [
      p.employee_name,
      p.position,
      "10",
      recordsStr || "-",
      p.total_score,
      p.grade,
    ];
  });
  const csvContent = [
    headers.join(","),
    ...rows.map((row) => row.map((cell) => `"${cell}"`).join(",")),
  ].join("\n");
  const blob = new Blob(["\uFEFF" + csvContent], {
    type: "text/csv;charset=utf-8;",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `绩效考核_${performanceMonth.value}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

// ==================== 罚款管理功能 ====================
async function loadPenaltyData() {
  try {
    // ✅ 直接使用 fetch，不通过 attendanceApi
    const token = localStorage.getItem("token");
    const response = await fetch(
      `/api/attendance/penalty/records?month=${penaltyMonth.value}&page=${penaltyPage.value}&page_size=${penaltyPageSize.value}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      },
    );
    const data = await response.json();

    const records = data.items || [];
    for (const record of records) {
      const emp = employees.value.find((e) => e.id === record.employee_id);
      record.position = emp?.position || "-";
      record.employee_name = emp?.name || record.employee_name || "未知";
    }

    penaltyRecords.value = records;
    penaltyTotal.value = data.total || 0;
    penaltyStats.value = data.stats || {
      totalAmount: 0,
      employeeCount: 0,
      recordCount: 0,
      avgAmount: 0,
    };
  } catch (error) {
    console.error("🔴 加载罚款失败:", error);
  }
}

function showAddPenaltyDialog() {
  penaltyForm.value = {
    employee_id: "",
    penalty_date: getToday(),
    amount: 0,
    category: "迟到",
    reason: "",
  };
  penaltyDialogVisible.value = true;
}

async function submitPenalty() {
  if (!penaltyFormRef.value) return;
  await penaltyFormRef.value.validate(async (valid) => {
    if (valid) {
      submittingPenalty.value = true;
      try {
        const token = localStorage.getItem("token");
        const response = await fetch("/api/attendance/penalty/record", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(penaltyForm.value),
        });

        if (response.ok) {
          ElMessage.success("罚款记录已添加");
          penaltyDialogVisible.value = false;
          await loadPenaltyData();

          // ✅ 修复：先刷新数据，再打开详情页
          if (detailDialogVisible.value === false && currentEmployee.value) {
            await loadCurrentEmployeePenalty(currentEmployee.value.id);
            detailDialogVisible.value = true;
          } else if (currentEmployee.value) {
            await loadCurrentEmployeePenalty(currentEmployee.value.id);
          }
        } else {
          const error = await response.json();
          throw new Error(error.detail || "添加失败");
        }
      } catch (error) {
        console.error("添加失败:", error);
        ElMessage.error(error.message || "添加失败");
      } finally {
        submittingPenalty.value = false;
      }
    }
  });
}

async function deletePenalty(row) {
  try {
    await ElMessageBox.confirm("确定要删除这条罚款记录吗？", "警告", {
      type: "warning",
    });

    // ✅ 直接使用 fetch
    const token = localStorage.getItem("token");
    const response = await fetch(`/api/attendance/penalty/records/${row.id}`, {
      method: "DELETE",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (response.ok) {
      ElMessage.success("删除成功");
      await loadPenaltyData(); // 重新加载列表
    } else {
      const error = await response.json();
      throw new Error(error.detail || "删除失败");
    }
  } catch (error) {
    if (error !== "cancel") {
      console.error("删除失败:", error);
      ElMessage.error(error.message || "删除失败");
    }
  }
}

function getPenaltyCategoryType(category) {
  const map = {
    迟到: "warning",
    早退: "warning",
    小厕超时: "danger",
    大厕超时: "danger",
    吃饭超时: "danger",
    抽烟或休息超时: "danger",
    其他: "info",
  };
  return map[category] || "info";
}

function exportPenalty() {
  if (!penaltyRecords.value.length) {
    ElMessage.warning("没有数据可导出");
    return;
  }
  const headers = [
    "员工姓名",
    "岗位",
    "罚款日期",
    "金额",
    "罚款类型",
    "罚款原因",
    "记录人",
  ];
  const rows = penaltyRecords.value.map((p) => [
    p.employee_name,
    p.position,
    p.penalty_date,
    p.amount,
    p.category,
    p.reason,
    p.created_by,
  ]);
  const csvContent = [
    headers.join(","),
    ...rows.map((row) => row.map((cell) => `"${cell || ""}"`).join(",")),
  ].join("\n");
  const blob = new Blob(["\uFEFF" + csvContent], {
    type: "text/csv;charset=utf-8;",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `罚款记录_${penaltyMonth.value}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

// 在 script setup 中添加这个函数
const formatDateShort = (dateStr) => {
  if (!dateStr) return "";
  // 如果是 YYYY-MM-DD 格式，只显示 MM-DD
  if (typeof dateStr === "string" && dateStr.includes("-")) {
    return dateStr.slice(5); // 返回 "MM-DD"
  }
  // 如果是 Date 对象
  if (dateStr instanceof Date) {
    const month = String(dateStr.getMonth() + 1).padStart(2, "0");
    const day = String(dateStr.getDate()).padStart(2, "0");
    return `${month}-${day}`;
  }
  return dateStr;
};

// ==================== 生命周期 ====================
onMounted(async () => {
  await loadEmployees();
  await loadAttendanceData();
  await loadPerformanceData();
  await loadPenaltyData();
});
</script>

<style scoped>
.attendance-management {
  padding: 20px;
}
.filter-card,
.attendance-table-card,
.summary-card,
.performance-card,
.penalty-card {
  margin-bottom: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: nowrap; /* 改为不换行 */
  gap: 16px;
}
.card-header-left {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}
.header-stats {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap; /* 不换行 */
}
.header-stats .el-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 15px; /* 从 13px 加大到 15px */
  padding: 0 14px; /* 增加内边距 */
  height: 32px; /* 增加高度 */
  line-height: 30px;
  font-weight: 500; /* 加粗 */
  white-space: nowrap;
}
.header-stats .el-tag .el-icon {
  font-size: 15px;
  margin-right: 2px;
}
.card-header-left > span {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 500;
  color: #303133;
  white-space: nowrap;
}
.text-right {
  text-align: right;
}
.batch-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.legend {
  display: flex;
  gap: 12px;
  flex-wrap: nowrap; /* 不换行 */
  flex-shrink: 1; /* 允许被压缩 */
  overflow-x: auto; /* 如果太窄就滚动 */
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  white-space: nowrap;
}
.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}
.dot.work {
  background: #28a745;
  box-shadow: 0 0 0 2px #d4edda;
}
.dot.rest-half {
  background: #17a2b8;
  box-shadow: 0 0 0 2px #b8d4e3;
}
.dot.rest-full {
  background: #0d6efd;
  box-shadow: 0 0 0 2px #6ea8c4;
}
.dot.leave {
  background: #ffc107;
  box-shadow: 0 0 0 2px #fff3cd;
}
.dot.absent {
  background: #dc3545;
  box-shadow: 0 0 0 2px #f8d7da;
}
.dot.off-post {
  background: #6f42c1;
  box-shadow: 0 0 0 2px #e2d5f3;
}
.dot.resigned {
  background: #c82333;
  box-shadow: 0 0 0 2px #f5c6cb;
}

/* 固定列 + 滚动列布局 */
.table-container-fixed-left {
  overflow-x: auto;
  overflow-y: auto;
  max-height: 70vh;
  position: relative;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}
.table-container-fixed-left::-webkit-scrollbar {
  height: 8px;
}
.table-container-fixed-left::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}
.table-container-fixed-left::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}
.table-container-fixed-left::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

.unified-table {
  border-collapse: collapse;
  width: max-content;
  min-width: 100%;
}
.unified-table th,
.unified-table td {
  border: 1px solid #ebeef5;
  padding: 6px 8px;
  white-space: nowrap;
  text-align: center;
  vertical-align: middle;
}
.unified-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
}
.unified-table thead tr th {
  position: sticky;
  top: 0;
  background-color: #f5f7fa;
  z-index: 10;
}

/* ✅ 表头固定列更高层级 */
.unified-table thead tr th.fixed-col {
  z-index: 15;
}
.unified-table tbody tr {
  background: white;
  transition: background-color 0.2s ease;
}
.unified-table tbody tr:hover {
  background: #e8f4e8 !important;
}

/* 固定列样式 */
.fixed-col {
  background-color: #ffffff;
  position: sticky;
  z-index: 1;
}
/* 计算每列的 left 偏移量 */
.unified-table th.fixed-col:nth-child(1),
.unified-table td.fixed-col:nth-child(1) {
  left: 0;
}

.unified-table th.fixed-col:nth-child(2),
.unified-table td.fixed-col:nth-child(2) {
  left: 55px; /* 复选框宽度 */
}

.unified-table th.fixed-col:nth-child(3),
.unified-table td.fixed-col:nth-child(3) {
  left: 155px; /* 55 + 100(入职日期) */
}

.unified-table th.fixed-col:nth-child(4),
.unified-table td.fixed-col:nth-child(4) {
  left: 265px; /* 155 + 110(姓名) */
}

.unified-table th.fixed-col:nth-child(5),
.unified-table td.fixed-col:nth-child(5) {
  left: 375px; /* 265 + 110(岗位) */
}

.unified-table th.fixed-col:nth-child(6),
.unified-table td.fixed-col:nth-child(6) {
  left: 505px; /* 375 + 130(办公地点) */
}

.unified-table th.fixed-col:nth-child(7),
.unified-table td.fixed-col:nth-child(7) {
  left: 635px; /* 505 + 130(实际上班) */
}

/* 第8列（请假/休假天数）*/
.unified-table th.fixed-col:nth-child(8),
.unified-table td.fixed-col:nth-child(8) {
  left: 765px; /* 635 + 130 */
}

.checkbox-col {
  width: 55px;
  min-width: 55px;
}
.date-col {
  width: 100px;
  min-width: 100px;
}
.name-col {
  width: 110px;
  min-width: 110px;
}
.position-col {
  width: 110px;
  min-width: 110px;
}
.location-col {
  width: 130px;
  min-width: 130px;
}
.stat-col {
  width: 130px;
  min-width: 130px;
}

.stat-col .stat-value {
  font-weight: bold;
  font-size: 16px;
}
.work-days {
  color: #28a745;
}
.rest-days {
  color: #17a2b8;
}

.employee-name-link {
  color: #409eff;
  cursor: pointer;
  font-weight: 500;
  text-decoration: none;
  transition: color 0.2s ease;
}
.employee-name-link:hover {
  text-decoration: underline;
  color: #66b1ff;
}

.scroll-hint {
  text-align: center;
  padding: 8px;
  font-size: 12px;
  color: #909399;
  background: #f5f7fa;
  border-top: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.penalty-stats-row {
  margin-bottom: 20px;
}
.penalty-stat-card {
  height: 100%;
}
.penalty-stat-card .stat-content {
  display: flex;
  align-items: center;
  gap: 16px;
}
.penalty-stat-card .stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.penalty-stat-card .stat-icon .el-icon {
  font-size: 24px;
}
.penalty-stat-card .stat-info {
  flex: 1;
}
.penalty-stat-card .stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #333;
}
.penalty-stat-card .stat-label {
  font-size: 14px;
  color: #999;
}
.penalty-amount {
  color: #f56c6c;
  font-weight: bold;
}

.score-records {
  text-align: left;
  max-height: 120px;
  overflow-y: auto;
}
.score-record-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 12px;
}
.score-record-item .record-date {
  color: #909399;
  width: 90px;
}
.score-record-item .score-plus {
  color: #67c23a;
  font-weight: bold;
  width: 50px;
}
.score-record-item .score-minus {
  color: #f56c6c;
  font-weight: bold;
  width: 50px;
}
.score-record-item .record-reason {
  color: #606266;
  flex: 1;
}

.help-text {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  display: block;
}
.info-text {
  color: #606266;
}
.info-text.highlight {
  color: #409eff;
  font-weight: bold;
  font-size: 16px;
}

.batch-employees {
  max-height: 150px;
  overflow-y: auto;
  padding: 8px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}
.detail-name {
  font-size: 18px;
  font-weight: bold;
  color: #409eff;
}
.pagination {
  margin-top: 20px;
  text-align: right;
}

/* 增强单元格内选择框的视觉样式 */
:deep(.el-select) {
  width: 100%;
}

:deep(.el-select .el-input__wrapper) {
  padding: 4px 8px;
  border-radius: 6px;
  transition: all 0.3s ease;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

:deep(.el-select .el-input__wrapper:hover) {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}

:deep(.el-select .el-input__inner) {
  font-weight: 500;
  text-align: center;
  transition: all 0.2s ease;
}

/* 出勤状态 - 绿色渐变 */
:deep(.status-work .el-input__wrapper) {
  background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%) !important;
  border-color: #28a745;
  box-shadow: 0 1px 3px rgba(40, 167, 69, 0.2);
}
:deep(.status-work .el-input__wrapper:hover) {
  background: linear-gradient(135deg, #c3e6cb 0%, #b0dfb5 100%);
  box-shadow: 0 2px 6px rgba(40, 167, 69, 0.3);
}
:deep(.status-work .el-input__inner) {
  color: #155724;
  font-weight: bold;
}

/* 休假半天 - 浅蓝色渐变 */
:deep(.status-rest-half .el-input__wrapper) {
  background: linear-gradient(135deg, #b8d4e3 0%, #a8c8da 100%);
  border-color: #17a2b8;
  box-shadow: 0 1px 3px rgba(23, 162, 184, 0.2);
}
:deep(.status-rest-half .el-input__wrapper:hover) {
  background: linear-gradient(135deg, #a8c8da 0%, #98bcd0 100%);
  box-shadow: 0 2px 6px rgba(23, 162, 184, 0.3);
}
:deep(.status-rest-half .el-input__inner) {
  color: #09c2e2 !important;
  font-weight: bold !important;
}

/* 休假一天 - 深蓝色渐变 */
:deep(.status-rest-full .el-input__wrapper) {
  background: linear-gradient(135deg, #6ea8c4 0%, #5a9bbd 100%);
  border-color: #0d6efd;
  box-shadow: 0 1px 3px rgba(13, 110, 253, 0.2);
}
:deep(.status-rest-full .el-input__wrapper:hover) {
  background: linear-gradient(135deg, #5a9bbd 0%, #4a8eaf 100%);
  box-shadow: 0 2px 6px rgba(13, 110, 253, 0.3);
}
:deep(.status-rest-full .el-input__inner) {
  color: #ffffff;
  font-weight: bold;
  text-shadow: 0 1px 1px rgba(0, 0, 0, 0.1);
}

/* 请假半天 - 黄色渐变 */
:deep(.status-leave .el-input__wrapper) {
  background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
  border-color: #ffc107;
  box-shadow: 0 1px 3px rgba(255, 193, 7, 0.2);
}
:deep(.status-leave .el-input__wrapper:hover) {
  background: linear-gradient(135deg, #ffeaa7 0%, #ffe08a 100%);
  box-shadow: 0 2px 6px rgba(255, 193, 7, 0.3);
}
:deep(.status-leave .el-input__inner) {
  color: #856404;
  font-weight: bold;
}

/* 旷工 - 红色渐变 */
:deep(.status-absent .el-input__wrapper) {
  background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%);
  border-color: #dc3545;
  box-shadow: 0 1px 3px rgba(220, 53, 69, 0.2);
}
:deep(.status-absent .el-input__wrapper:hover) {
  background: linear-gradient(135deg, #f5c6cb 0%, #f1b0b7 100%);
  box-shadow: 0 2px 6px rgba(220, 53, 69, 0.3);
}
:deep(.status-absent .el-input__inner) {
  color: #721c24;
  font-weight: bold;
}

/* 离岗 - 紫色渐变 */
:deep(.status-off-post .el-input__wrapper) {
  background: linear-gradient(135deg, #e2d5f3 0%, #d4c4e8 100%);
  border-color: #6f42c1;
  box-shadow: 0 1px 3px rgba(111, 66, 193, 0.2);
}
:deep(.status-off-post .el-input__wrapper:hover) {
  background: linear-gradient(135deg, #d4c4e8 0%, #c6b4dd 100%);
  box-shadow: 0 2px 6px rgba(111, 66, 193, 0.3);
}
:deep(.status-off-post .el-input__inner) {
  color: #3d1a6e;
  font-weight: bold;
}

/* 离职 - 灰红色渐变 */
:deep(.status-resigned .el-input__wrapper) {
  background: linear-gradient(135deg, #f5c6cb 0%, #e9b5bb 100%);
  border-color: #c82333;
  box-shadow: 0 1px 3px rgba(200, 35, 51, 0.2);
}
:deep(.status-resigned .el-input__wrapper:hover) {
  background: linear-gradient(135deg, #e9b5bb 0%, #dda4aa 100%);
  box-shadow: 0 2px 6px rgba(200, 35, 51, 0.3);
}
:deep(.status-resigned .el-input__inner) {
  color: #721c24;
  font-weight: bold;
  text-decoration: line-through;
}

/* 周末列背景色 */
.day-cell.weekend {
  background-color: #fafafa;
}
.day-cell.weekend :deep(.el-input__wrapper) {
  background-color: rgba(0, 0, 0, 0.02);
}

@media screen and (max-width: 768px) {
  .attendance-management {
    padding: 12px;
  }
  .unified-table th,
  .unified-table td {
    padding: 6px 4px;
  }
  .checkbox-col {
    width: 40px;
    min-width: 40px;
  }
  .date-col {
    width: 85px;
    min-width: 85px;
  }
  .name-col,
  .position-col {
    width: 80px;
    min-width: 80px;
  }
  .location-col {
    width: 100px;
    min-width: 100px;
  }
  .stat-col {
    width: 95px;
    min-width: 95px;
  }
  .scroll-col {
    position: relative;
  }

  /* 表头的固定列需要更高的层级 */
  .unified-table thead tr th.fixed-col {
    z-index: 15; /* 比普通固定列和普通表头都高 */
    background-color: #f5f7fa;
  }
  .unified-table th.fixed-col:nth-child(6) {
    left: 420px;
  }
  .unified-table td.fixed-col:nth-child(6) {
    left: 420px;
  }
  .unified-table th.fixed-col:nth-child(7) {
    left: 515px;
  }
  .unified-table td.fixed-col:nth-child(7) {
    left: 515px;
  }
}
@media screen and (max-width: 1200px) {
  .legend {
    overflow-x: auto;
    max-width: 400px;
  }
}

.unified-table tbody tr:hover {
  background-color: #e8f4e8 !important;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

/* 如果想要更明显的高亮效果 */
.unified-table tbody tr:hover td {
  background-color: #e6f7ff !important;
}

/* 或者使用渐变效果 */
.unified-table tbody tr:hover {
  background: linear-gradient(90deg, #f0f9ff 0%, #e6f7ff 100%);
}
</style>

<style>
/* 下拉选项样式增强 - 全局样式 */
.attendance-select-popper {
  border-radius: 12px !important;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12) !important;
  padding: 8px 0 !important;
}

.attendance-select-popper .el-select-dropdown__item {
  border-radius: 8px !important;
  margin: 2px 8px !important;
  padding: 8px 12px !important;
  transition: all 0.2s ease !important;
}

.attendance-select-popper .el-select-dropdown__item:hover {
  transform: translateX(4px) !important;
  background-color: #f5f7fa !important;
}

/* 下拉选项hover背景色增强 */
.attendance-select-popper .el-select-dropdown__item.work-option:hover {
  background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%) !important;
}
.attendance-select-popper .el-select-dropdown__item.rest-half-option:hover {
  background: linear-gradient(135deg, #b8d4e3 0%, #a8c8da 100%) !important;
}
.attendance-select-popper .el-select-dropdown__item.rest-full-option:hover {
  background: linear-gradient(135deg, #6ea8c4 0%, #5a9bbd 100%) !important;
}
.attendance-select-popper .el-select-dropdown__item.leave-option:hover {
  background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%) !important;
}
.attendance-select-popper .el-select-dropdown__item.absent-option:hover {
  background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%) !important;
}
.attendance-select-popper .el-select-dropdown__item.off-post-option:hover {
  background: linear-gradient(135deg, #e2d5f3 0%, #d4c4e8 100%) !important;
}
.attendance-select-popper .el-select-dropdown__item.resigned-option:hover {
  background: linear-gradient(135deg, #f5c6cb 0%, #e9b5bb 100%) !important;
}

/* 下拉选项选中状态 */
.attendance-select-popper .el-select-dropdown__item.is-selected {
  background-color: #ecf5ff !important;
  font-weight: bold !important;
}

.status-option {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.status-icon {
  font-size: 16px;
  width: 24px;
}

.status-badge {
  margin-left: auto;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 12px;
  background-color: rgba(0, 0, 0, 0.06);
  color: #666;
  font-weight: normal;
}

.work-option {
  color: #28a745;
}
.work-option .status-badge {
  background-color: #28a74520;
  color: #28a745;
}

.rest-half-option {
  color: #17a2b8;
}
.rest-half-option .status-badge {
  background-color: #17a2b820;
  color: #17a2b8;
}

.rest-full-option {
  color: #0d6efd;
}
.rest-full-option .status-badge {
  background-color: #0d6efd20;
  color: #0d6efd;
}

.leave-option {
  color: #ffc107;
}
.leave-option .status-badge {
  background-color: #ffc10720;
  color: #d39e00;
}

.absent-option {
  color: #dc3545;
}
.absent-option .status-badge {
  background-color: #dc354520;
  color: #dc3545;
}

.off-post-option {
  color: #6f42c1;
}
.off-post-option .status-badge {
  background-color: #6f42c120;
  color: #6f42c1;
}

.resigned-option {
  color: #c82333;
}
.resigned-option .status-badge {
  background-color: #c8233320;
  color: #c82333;
}

/* 表格选择框动画 */
.unified-table td .el-select {
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

/* 滚动条美化 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

/* 统计卡片动画 */
.penalty-stat-card {
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease;
}
.penalty-stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.1);
}

/* 直接针对下拉框包装器的背景色 */
.attendance-table-card .status-work .el-select__wrapper {
  background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%) !important;
  border-color: #28a745 !important;
}

.attendance-table-card .status-absent .el-select__wrapper {
  background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%) !important;
  border-color: #dc3545 !important;
}

.attendance-table-card .status-off-post .el-select__wrapper {
  background: linear-gradient(135deg, #e2d5f3 0%, #d4c4e8 100%) !important;
  border-color: #6f42c1 !important;
}

.attendance-table-card .status-rest-half .el-select__wrapper {
  background: linear-gradient(135deg, #b8d4e3 0%, #a8c8da 100%) !important;
  border-color: #17a2b8 !important;
}

.attendance-table-card .status-rest-full .el-select__wrapper {
  background: linear-gradient(135deg, #6ea8c4 0%, #5a9bbd 100%) !important;
  border-color: #0d6efd !important;
}

.attendance-table-card .status-leave .el-select__wrapper {
  background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%) !important;
  border-color: #ffc107 !important;
}

.attendance-table-card .status-resigned .el-select__wrapper {
  background: linear-gradient(135deg, #f5c6cb 0%, #e9b5bb 100%) !important;
  border-color: #c82333 !important;
}

/* 文字颜色 */
.attendance-table-card .status-work .el-select__selected-item {
  color: #155724 !important;
  font-weight: bold !important;
}

.attendance-table-card .status-absent .el-select__selected-item {
  color: #721c24 !important;
  font-weight: bold !important;
}

.attendance-table-card .status-off-post .el-select__selected-item {
  color: #3d1a6e !important;
  font-weight: bold !important;
}
/* 半休 - 文字颜色 */
.attendance-table-card .status-rest-half .el-select__selected-item {
  color: #0c5460 !important; /* 深蓝色 */
  font-weight: bold !important;
}

/* 全休 - 文字颜色（深色背景用白色） */
.attendance-table-card .status-rest-full .el-select__selected-item {
  color: #ffffff !important; /* 白色 */
  font-weight: bold !important;
  text-shadow: 0 0 1px rgba(0, 0, 0, 0.3);
}

/* 半假 - 文字颜色 */
.attendance-table-card .status-leave .el-select__selected-item {
  color: #856404 !important; /* 深棕色 */
  font-weight: bold !important;
}

/* 离职 - 文字颜色 */
.attendance-table-card .status-resigned .el-select__selected-item {
  color: #721c24 !important;
  font-weight: bold !important;
  text-decoration: line-through;
}
/* admin_Attendance.vue - 添加样式 */

.attendance-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.performance-info {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.penalty-info {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.more-records {
  text-align: center;
  padding-top: 8px;
}
/* 员工分页样式 */
.employee-pagination {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
  text-align: right;
}

/* 状态徽章样式 */
.status-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  min-width: 50px;
  text-align: center;
}

/* 出勤 */
.status-badge.status-work {
  background-color: #d4edda;
  color: #28a745;
}

/* 半休 */
.status-badge.status-rest-half {
  background-color: #fff3cd;
  color: #4051ec;
}

/* 全休 */
.status-badge.status-rest-full {
  background-color: #fff3cd;
  color: #ec40d0;
}

/* 半假 */
.status-badge.status-leave {
  background-color: #e2d5f3;
  color: #6f42c1;
}

/* 旷工 */
.status-badge.status-absent {
  background-color: #f8d7da;
  color: #dc3545;
}

/* 全假 */
.status-badge.status-off-post {
  background-color: #e2d5f3;
  color: #f02f7f;
}

/* 离职 */
.status-badge.status-resigned {
  background-color: #f5c6cb;
  color: #c82333;
  text-decoration: line-through;
}

/* 无状态 */
.status-badge.status- {
  background-color: #f5f5f5;
  color: #999;
}

/* 员工详情对话框样式 */
.employee-detail-dialog {
  border-radius: 16px;
}

.employee-detail-dialog :deep(.el-dialog__header) {
  border-bottom: 1px solid #f0f0f0;
  padding: 20px 24px;
  margin-right: 0;
}

.employee-detail-dialog :deep(.el-dialog__body) {
  padding: 20px 24px;
  max-height: 50vh;
  overflow-y: auto;
}

.employee-detail-dialog :deep(.el-dialog__footer) {
  border-top: 1px solid #f0f0f0;
  padding: 16px 24px;
}

/* 头部样式 */
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.avatar-section {
  display: flex;
  align-items: center;
  gap: 16px;
}

.employee-avatar {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.employee-title {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.employee-name {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.employee-badges {
  display: flex;
  gap: 8px;
}

.employee-id {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #909399;
  font-size: 13px;
  background: #f5f7fa;
  padding: 6px 12px;
  border-radius: 20px;
}

/* 网格布局 */
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 8px;
}

.grid-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 12px;
  transition: all 0.2s;
}

.grid-item:hover {
  background: #f0f2f5;
  transform: translateY(-1px);
}

.grid-icon {
  width: 40px;
  height: 40px;
  background: white;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #667eea;
  font-size: 20px;
}

.grid-content {
  flex: 1;
}

.grid-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.grid-value {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.stat-work {
  color: #67c23a;
}

.stat-leave {
  color: #e6a23c;
}

.stat-divider {
  color: #dcdfe6;
}

.penalty-amount {
  color: #f56c6c;
  font-weight: bold;
}

/* 分割线样式 */
.divider-text {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  color: #606266;
}

/* 记录区域 */
.record-section {
  margin: 8px 0 4px;
  border-radius: 12px;
  background: #fafbfc;
  transition: all 0.2s;
}

.record-section.has-records {
  background: transparent;
}

.record-list {
  max-height: 160px;
  overflow-y: auto;
  padding: 4px;
}

.record-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  background: white;
  border-radius: 10px;
  margin-bottom: 8px;
  transition: all 0.2s;
  border: 1px solid #f0f0f0;
}

.record-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  transform: translateX(2px);
}

.record-item:last-child {
  margin-bottom: 0;
}

/* 日期徽章 */
.record-date-badge {
  min-width: 70px;
  text-align: center;
  padding: 4px 8px;
  background: #f5f7fa;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 500;
  color: #606266;
}

.record-day {
  font-weight: 600;
}

.penalty-date {
  background: #fef0f0;
  color: #f56c6c;
}

/* 记录内容 */
.record-content {
  flex: 1;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.record-score {
  font-weight: 600;
  font-size: 14px;
  min-width: 55px;
}

.score-plus {
  color: #67c23a;
}

.score-minus {
  color: #f56c6c;
}

.penalty-amount-badge {
  background: #fef0f0;
  color: #f56c6c;
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: 600;
  font-size: 13px;
}

.record-reason {
  flex: 1;
  font-size: 13px;
  color: #606266;
  line-height: 1.4;
  word-break: break-word;
}

.record-category {
  margin-left: auto;
}

/* 空状态 */
.empty-records {
  padding: 16px;
  background: #fafbfc;
  border-radius: 12px;
}

.empty-records :deep(.el-empty__image) {
  width: 60px;
}

.empty-records :deep(.el-empty__description p) {
  font-size: 12px;
  color: #c0c4cc;
}

/* 查看全部按钮 */
.view-all-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #e4e7ed;
}

/* 底部按钮 */
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

/* 响应式 */
@media screen and (max-width: 500px) {
  .detail-grid {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .detail-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .record-content {
    flex-direction: column;
    align-items: flex-start;
  }

  .record-category {
    margin-left: 0;
  }
}

/* 更精致的按钮样式 */
.add-score-btn,
.add-penalty-btn {
  padding: 6px 14px;
  border-radius: 24px;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  border: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  backdrop-filter: blur(4px);
}

/* 加减分按钮 - 绿色渐变 */
.add-score-btn {
  background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
  color: #2e7d32;
  box-shadow: 0 1px 3px rgba(46, 125, 50, 0.1);
}

.add-score-btn:hover {
  background: linear-gradient(135deg, #c8e6c9 0%, #a5d6a7 100%);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(46, 125, 50, 0.25);
}

.add-score-btn:active {
  transform: translateY(0);
  box-shadow: 0 1px 3px rgba(46, 125, 50, 0.15);
}

/* 罚款按钮 - 红色渐变 */
.add-penalty-btn {
  background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);
  color: #c62828;
  box-shadow: 0 1px 3px rgba(198, 40, 40, 0.1);
}

.add-penalty-btn:hover {
  background: linear-gradient(135deg, #ffcdd2 0%, #ef9a9a 100%);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(198, 40, 40, 0.25);
}

.add-penalty-btn:active {
  transform: translateY(0);
  box-shadow: 0 1px 3px rgba(198, 40, 40, 0.15);
}

/* 按钮图标动画 */
.add-score-btn .el-icon,
.add-penalty-btn .el-icon {
  transition: transform 0.2s ease;
}

.add-score-btn:hover .el-icon,
.add-penalty-btn:hover .el-icon {
  transform: scale(1.1);
}

/* 小型空状态样式 */
.empty-records-small {
  padding: 20px;
  text-align: center;
  background: #fafbfc;
  border-radius: 12px;
  margin-bottom: 8px;
}

.empty-records-small :deep(.el-empty__image) {
  width: 40px;
}

.empty-records-small :deep(.el-empty__description p) {
  font-size: 12px;
  color: #c0c4cc;
}
</style>
