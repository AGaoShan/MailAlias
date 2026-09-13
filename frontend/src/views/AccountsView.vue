<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">账号管理</h2>
        <p class="page-subtitle">已接入 {{ store.accounts.length }} 个 mail.com 账号</p>
      </div>
      <div class="header-actions">
        <el-button :disabled="store.accounts.length === 0" @click="openExport">
          <el-icon><Download /></el-icon>批量导出
        </el-button>
        <el-button @click="openBatch">
          <el-icon><Upload /></el-icon>批量导入
        </el-button>
        <el-button type="primary" @click="openSingle">
          <el-icon><Plus /></el-icon>添加账号
        </el-button>
      </div>
    </div>

    <el-card>
      <el-table :data="store.accounts" v-loading="store.loading" empty-text="暂无账号，点击右上角添加">
        <el-table-column prop="email" label="邮箱" min-width="220">
          <template #default="{ row }">
            <span class="mono">{{ row.email }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="account_key" label="账号标识" min-width="140">
          <template #default="{ row }">
            <span class="mono text-muted">{{ row.account_key }}</span>
          </template>
        </el-table-column>
        <el-table-column label="登录状态" width="130">
          <template #default="{ row }">
            <el-tag :type="sessionStateType(row.session_state)" effect="light" class="state-tag">
              <span v-if="row.session_state === 'logging_in'" class="spin-dot" />
              {{ row.session_state_text || sessionStateText(row.session_state) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="别名用量" width="210">
          <template #default="{ row }">
            <el-progress
              :percentage="usagePercent(row)"
              :stroke-width="7"
              :show-text="false"
              :status="row.alias_count >= row.alias_limit ? 'exception' : undefined"
            />
            <div class="usage-text">
              <span class="mono">{{ row.alias_count }}/{{ row.alias_limit }}</span>
              <span class="text-muted">剩余 {{ Math.max(row.alias_limit - row.alias_count, 0) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <span class="status-dot" :class="row.enabled ? 'on' : 'off'">
              {{ row.enabled ? "启用" : "停用" }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="218" align="right">
          <template #default="{ row }">
            <el-button size="small" :loading="verifyingId === row.id" @click="handleVerify(row.id)">验证</el-button>
            <el-button size="small" type="primary" plain @click="goAliases(row.id)">别名</el-button>
            <el-button size="small" type="danger" plain @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>


    <el-dialog v-model="dialogVisible" title="添加 mail.com 账号" width="460px" @closed="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="账号" prop="email">
          <el-input
            v-model="form.email"
            placeholder="邮箱，或直接粘贴 邮箱----密码"
            @paste="onEmailPaste"
            @input="onEmailInput"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="账号密码" />
        </el-form-item>
        <el-alert
          type="info"
          :closable="false"
          title="支持粘贴 “邮箱----密码”，会自动拆分到两个输入框；提交后将调用 mail.com 登录验证并加密存储凭据"
        />
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchVisible" title="批量导入账号" width="640px" @closed="resetBatch">
      <el-form label-width="80px">
        <el-form-item label="账号列表">
          <el-input
            v-model="batchText"
            type="textarea"
            :rows="10"
            placeholder="每行一个账号，支持：&#10;邮箱----密码&#10;邮箱:密码&#10;邮箱,密码"
          />
        </el-form-item>
        <el-form-item label="解析结果">
          <div class="batch-summary">
            <el-tag type="success" effect="light">有效 {{ batchParsed.accounts.length }} 条</el-tag>
            <el-tag v-if="batchParsed.invalid.length" type="danger" effect="light">
              无效 {{ batchParsed.invalid.length }} 条
            </el-tag>
          </div>
        </el-form-item>
        <el-form-item v-if="batchParsed.invalid.length" label="无效行">
          <div class="invalid-lines mono">{{ batchParsed.invalid.join(" / ") }}</div>
        </el-form-item>
      </el-form>

      <el-card v-if="batchResults.length" shadow="never" class="batch-results">
        <div v-for="(item, index) in batchResults" :key="index" class="batch-result-row">
          <el-tag :type="item.ok ? 'success' : 'danger'" effect="light" size="small">
            {{ item.ok ? "成功" : "失败" }}
          </el-tag>
          <span class="mono">{{ item.email }}</span>
          <span v-if="!item.ok" class="text-muted result-msg">{{ item.message }}</span>
        </div>
      </el-card>

      <template #footer>
        <el-button @click="batchVisible = false">关闭</el-button>
        <el-button
          type="primary"
          :loading="batchRunning"
          :disabled="batchParsed.accounts.length === 0"
          @click="handleBatchImport"
        >
          开始导入（{{ batchParsed.accounts.length }}）
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="exportVisible" title="批量导出账号" width="640px" @closed="resetExport">
      <el-alert
        type="warning"
        :closable="false"
        class="mb-12"
        title="导出内容包含明文密码，请妥善保管，避免泄露"
      />
      <el-alert type="info" :closable="false" class="mb-12" title="格式：邮箱----密码（可直接用于批量导入）" />
      <el-input v-model="exportText" type="textarea" :rows="10" readonly class="mono" />
      <div class="export-actions">
        <el-button size="small" @click="copyExport">复制全部</el-button>
        <el-button size="small" @click="downloadExport">下载 txt</el-button>
        <span class="text-muted export-stat">共 {{ exportCount }} 个账号</span>
      </div>
      <template #footer>
        <el-button @click="exportVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from "element-plus";
import { accountApi } from "@/api";
import { useAccountStore } from "@/stores/account";
import type { Account } from "@/api/types";
import { copyText, sessionStateText, sessionStateType } from "@/utils/format";
import { parseAccountLine, parseAccountText } from "@/utils/accountParser";

const router = useRouter();
const store = useAccountStore();

const dialogVisible = ref(false);
const submitting = ref(false);
const verifyingId = ref<number | null>(null);
const formRef = ref<FormInstance>();
const form = reactive({ email: "", password: "" });
const rules: FormRules = {
  email: [
    { required: true, message: "请输入邮箱", trigger: "blur" },
    { type: "email", message: "邮箱格式不正确", trigger: "blur" },
  ],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
};

const batchVisible = ref(false);
const batchText = ref("");
const batchRunning = ref(false);
const batchResults = ref<{ email: string; ok: boolean; message?: string }[]>([]);
const batchParsed = computed(() => parseAccountText(batchText.value));

function openSingle(): void {
  dialogVisible.value = true;
}

function usagePercent(row: Account): number {
  if (!row.alias_limit) return 0;
  return Math.min(Math.round((row.alias_count / row.alias_limit) * 100), 100);
}

function openBatch(): void {
  batchVisible.value = true;
}

function applyLine(line: string): boolean {
  const parsed = parseAccountLine(line);
  if (!parsed) return false;
  form.email = parsed.email;
  form.password = parsed.password;
  return true;
}

function onEmailPaste(event: ClipboardEvent): void {
  const text = event.clipboardData?.getData("text") ?? "";
  if (!text.includes("\n") && applyLine(text)) {
    event.preventDefault();
    ElMessage.success("已自动拆分邮箱与密码");
  }
}

function onEmailInput(value: string): void {
  // 手动输入时若包含分隔符，也自动拆分
  if (value.includes("----")) {
    applyLine(value);
  }
}

async function handleSubmit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  submitting.value = true;
  try {
    await store.create(form.email, form.password);
    ElMessage.success("账号添加成功");
    dialogVisible.value = false;
    await store.fetchAll();
  } finally {
    submitting.value = false;
  }
}

function resetForm(): void {
  formRef.value?.resetFields();
  form.email = "";
  form.password = "";
}

async function handleBatchImport(): Promise<void> {
  const { accounts, invalid } = batchParsed.value;
  if (accounts.length === 0) {
    ElMessage.warning("没有可导入的有效账号");
    return;
  }
  if (invalid.length > 0) {
    await ElMessageBox.confirm(`有 ${invalid.length} 行无法解析，将跳过这些行，是否继续？`, "提示", {
      type: "warning",
    });
  }
  batchRunning.value = true;
  batchResults.value = [];
  let success = 0;
  try {
    for (const account of accounts) {
      try {
        await store.create(account.email, account.password, true);
        batchResults.value.push({ email: account.email, ok: true });
        success += 1;
      } catch (error) {
        const message =
          (error as { message?: string })?.message ?? "添加失败（可能是密码错误或已存在）";
        batchResults.value.push({ email: account.email, ok: false, message });
      }
    }
    ElMessage.success(`导入完成：成功 ${success} / ${accounts.length}`);
    await store.fetchAll();
  } finally {
    batchRunning.value = false;
  }
}

function resetBatch(): void {
  batchText.value = "";
  batchResults.value = [];
}

const exportVisible = ref(false);
const exportText = ref("");
const exportCount = ref(0);

async function openExport(): Promise<void> {
  exportVisible.value = true;
  exportText.value = "";
  exportCount.value = 0;
  try {
    const items = await accountApi.exportCredentials();
    exportText.value = items.map((item) => `${item.email}----${item.password}`).join("\n");
    exportCount.value = items.length;
  } catch {
    exportVisible.value = false;
  }
}

function resetExport(): void {
  exportText.value = "";
  exportCount.value = 0;
}

async function copyExport(): Promise<void> {
  if (!exportText.value) {
    ElMessage.warning("没有可复制的内容");
    return;
  }
  const ok = await copyText(exportText.value);
  if (ok) ElMessage.success(`已复制 ${exportCount.value} 个账号（格式：邮箱----密码）`);
}

function downloadExport(): void {
  if (!exportText.value) {
    ElMessage.warning("没有可下载的内容");
    return;
  }
  const blob = new Blob([exportText.value], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `mailcom_accounts_${Date.now()}.txt`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function handleVerify(id: number): Promise<void> {
  verifyingId.value = id;
  try {
    await store.verify(id);
    ElMessage.success("验证完成");
  } finally {
    verifyingId.value = null;
  }
}

async function handleDelete(row: Account): Promise<void> {
  await ElMessageBox.confirm(`确定删除账号 ${row.email} 及其所有别名映射吗？`, "警告", { type: "warning" });
  await store.remove(row.id);
  ElMessage.success("已删除");
}

function goAliases(id: number): void {
  store.select(id);
  router.push({ name: "aliases", query: { account: String(id) } });
}
</script>

<style scoped>
.header-actions {
  display: flex;
  gap: 12px;
}

/* ---------- 批量导出 ---------- */
.export-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.export-stat {
  font-size: 12px;
  margin-left: auto;
}

.mb-12 {
  margin-bottom: 12px;
}

/* ---------- 登录状态 ---------- */
.state-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.spin-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  animation: state-pulse 1s ease-in-out infinite;
}

@keyframes state-pulse {
  0%,
  100% {
    opacity: 0.25;
    transform: scale(0.75);
  }
  50% {
    opacity: 1;
    transform: scale(1.05);
  }
}

.usage-text {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 11.5px;
  margin-top: 5px;
  gap: 10px;
}

/* 启用状态：小圆点 + 文字，比标签更安静 */
.status-dot {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--text-regular);
}

.status-dot::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.on::before {
  background: var(--ok);
  box-shadow: 0 0 0 3px var(--ok-soft);
}

.status-dot.off::before {
  background: var(--text-faint);
  box-shadow: 0 0 0 3px #f2f5f6;
}

.batch-summary {
  display: flex;
  gap: 8px;
}

.invalid-lines {
  font-size: 12px;
  color: var(--danger);
  word-break: break-all;
  line-height: 1.7;
  max-height: 120px;
  overflow-y: auto;
}

.batch-results {
  max-height: 240px;
  overflow-y: auto;
  background: var(--surface-sunken);
  border: 1px solid var(--border-soft);
  box-shadow: none;
}

.batch-result-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  font-size: 12.5px;
  border-bottom: 1px solid var(--border-soft);
}

.batch-result-row:last-child {
  border-bottom: none;
}

.result-msg {
  font-size: 11.5px;
  margin-left: auto;
  text-align: right;
}
</style>
