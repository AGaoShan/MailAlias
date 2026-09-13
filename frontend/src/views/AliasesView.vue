<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">别名管理</h2>
        <p class="page-subtitle">创建别名并自动绑定取件地址</p>
      </div>
      <div class="toolbar">
        <el-select v-model="accountId" placeholder="选择账号" style="width: 240px" @change="onAccountChange">
          <el-option
            v-for="account in store.accounts"
            :key="account.id"
            :label="account.email"
            :value="account.id"
          />
        </el-select>
        <el-button :disabled="!accountId" :loading="aliasStore.loading" @click="loadAliases">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
        <el-button
          :disabled="aliasStore.aliases.length === 0"
          @click="copyAllAliases"
        >
          <el-icon><DocumentCopy /></el-icon>复制全部
        </el-button>
        <el-button
          type="danger"
          plain
          :disabled="deletableCount === 0"
          @click="selectAllDeletable"
        >
          <el-icon><Select /></el-icon>全选可删除 ({{ deletableCount }})
        </el-button>
        <el-button type="primary" plain :disabled="!hasAnyAccount" @click="openBatch">
          <el-icon><Files /></el-icon>批量生成
        </el-button>
        <el-button type="primary" :disabled="!canCreate" @click="openCreate">
          <el-icon><Plus /></el-icon>创建别名
        </el-button>
      </div>
    </div>

    <el-card v-if="currentAccount" class="mb-16 summary-card">
      <div class="account-summary">
        <div class="summary-item">
          <span class="summary-label">当前账号</span>
          <span class="mono summary-main">{{ currentAccount.email }}</span>
        </div>
        <div class="summary-divider" />
        <div class="summary-item">
          <span class="summary-label">别名用量</span>
          <div class="usage-row">
            <el-progress
              class="usage-bar"
              :percentage="usagePercent"
              :stroke-width="7"
              :show-text="false"
              :status="isFull ? 'exception' : undefined"
            />
            <span class="mono usage-num" :class="{ full: isFull }">
              {{ currentAccount.alias_count }}/{{ currentAccount.alias_limit }}
            </span>
          </div>
        </div>
        <div class="summary-divider" />
        <div class="summary-item">
          <span class="summary-label">会话状态</span>
          <el-tag :type="sessionStateType(currentAccount.session_state)" effect="light">
            {{ sessionStateText(currentAccount.session_state) }}
          </el-tag>
        </div>
      </div>
    </el-card>

    <el-card>
      <div v-if="selectedIds.length > 0" class="batch-bar">
        <span class="batch-bar-text">已选 {{ selectedIds.length }} 个别名</span>
        <el-button size="small" @click="clearSelection">取消选择</el-button>
        <el-button size="small" type="danger" :loading="batchDeleting" @click="handleBatchDelete">
          <el-icon><Delete /></el-icon>批量删除
        </el-button>
      </div>
      <el-table
        ref="tableRef"
        :data="aliasStore.aliases"
        v-loading="aliasStore.loading"
        empty-text="暂无别名"
        :row-class-name="rowClassName"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="46" :selectable="isSelectable" />
        <el-table-column prop="address" label="别名地址" min-width="200">
          <template #default="{ row }">
            <span class="mono">{{ row.address }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="165">
          <template #default="{ row }">
            <span class="text-muted time-cell">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="display_name" label="显示名" width="140">
          <template #default="{ row }">
            <span v-if="row.display_name">{{ row.display_name }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="默认发件人" width="115" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_default_sender" type="success" effect="light">是</el-tag>
            <span v-else class="text-muted">否</span>
          </template>
        </el-table-column>
        <el-table-column prop="pickup_url" label="取件地址" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono text-muted">{{ row.pickup_url }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="272" align="right">
          <template #default="{ row }">
            <el-button size="small" plain @click="copyPickup(row)">复制取件</el-button>
            <el-button size="small" plain :disabled="!row.deletable" @click="openSender(row)">默认发件人</el-button>
            <el-button size="small" type="danger" plain :disabled="!row.deletable" @click="handleDelete(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="createVisible" title="创建别名" width="480px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="90px">
        <el-form-item label="账号">
          <el-input :model-value="currentAccount?.email" disabled />
        </el-form-item>
        <el-form-item label="别名" prop="localPart">
          <div class="alias-input">
            <el-input v-model="createForm.localPart" placeholder="my-alias" @input="onLocalPartInput">
              <template #append>
                <el-select v-model="createForm.domain" style="width: 150px" :loading="domainsLoading">
                  <el-option v-for="domain in aliasStore.domains" :key="domain" :label="domain" :value="domain" />
                </el-select>
              </template>
            </el-input>
          </div>
        </el-form-item>
        <el-form-item label="完整地址">
          <span class="mono">{{ fullAddress || "-" }}</span>
        </el-form-item>
        <el-alert
          type="warning"
          :closable="false"
          title="别名 local part 需 3-62 位，仅允许小写字母、数字、点、下划线、连字符；每账号最多 10 个"
        />
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建并绑定取件地址</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchVisible" title="批量生成别名" width="720px" @closed="resetBatch">
      <el-form label-width="90px">
        <el-form-item label="账号">
          <el-select v-model="batchAccountMode" style="width: 100%">
            <el-option label="自动选择（按剩余额度分配）" value="auto" />
            <el-option
              v-for="account in store.accounts"
              :key="account.id"
              :label="`${account.email}（${account.alias_count}/${account.alias_limit}）`"
              :value="account.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="生成数量">
          <div class="gen-row">
            <el-input-number v-model="batchCount" :min="1" :max="100" :step="1" />
            <span class="text-muted gen-hint">
              剩余可创建约 {{ remainingCapacity }} 个，超出部分会自动跳过并提示
            </span>
          </div>
        </el-form-item>
        <el-form-item label="后缀域名">
          <div class="gen-row">
            <el-select
              v-model="batchDomain"
              filterable
              style="width: 260px"
              :loading="domainsLoading"
              placeholder="选择域名"
            >
              <el-option v-for="domain in aliasStore.domains" :key="domain" :label="domain" :value="domain" />
            </el-select>
            <el-button :loading="domainsLoading" @click="refreshDomains">
              <el-icon><Refresh /></el-icon>刷新域名
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="固定前缀">
          <div class="gen-row">
            <el-input v-model="batchPrefix" placeholder="可选，如 tmp（便于识别）" style="width: 200px" @input="onPrefixInput" />
            <span class="text-muted gen-hint">随机部分长度</span>
            <el-input-number v-model="batchLength" :min="6" :max="40" :step="1" />
          </div>
        </el-form-item>
        <el-form-item label="预览">
          <span class="mono text-muted">{{ previewAddress }}</span>
        </el-form-item>
        <el-alert
          type="info"
          :closable="false"
          title="别名由随机字母/数字（含可选 . - _ 分隔符）生成；每账号最多 10 个"
        />
      </el-form>

      <template v-if="batchResults.length">
        <el-divider content-position="left">生成结果</el-divider>
        <el-alert type="info" :closable="false" class="mb-12" title="输出格式：别名邮箱----取件地址" />
        <el-input v-model="batchOutput" type="textarea" :rows="8" readonly class="mono" />
        <div class="batch-actions">
          <el-button size="small" @click="copyBatchOutput">复制结果</el-button>
          <el-button size="small" @click="downloadBatchOutput">下载 txt</el-button>
          <span class="text-muted batch-stat">
            成功 {{ batchSuccessCount }} / {{ batchResults.length }}
          </span>
        </div>
      </template>

      <template #footer>
        <el-button @click="batchVisible = false">关闭</el-button>
        <el-button type="primary" :loading="batchRunning" @click="handleBatchGenerate">
          生成 {{ batchCount }} 个
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="senderVisible" title="设置默认发件人" width="460px">
      <el-form label-width="100px">
        <el-form-item label="别名">
          <span class="mono">{{ senderTarget?.address }}</span>
        </el-form-item>
        <el-form-item label="显示名">
          <el-input
            v-model="senderDisplayName"
            placeholder="可选，设置后可选择 显示名 <邮箱>"
            @blur="saveDisplayName"
          >
            <template #append>
              <el-button @click="saveDisplayName">保存</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="发件人格式">
          <el-radio-group v-model="senderMode">
            <el-radio value="email">纯邮箱</el-radio>
            <el-radio value="name-email" :disabled="!senderDisplayName.trim()">
              显示名 &lt;邮箱&gt;
            </el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="senderVisible = false">取消</el-button>
        <el-button type="primary" :loading="senderSaving" @click="handleSenderSave">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from "element-plus";
import { useAccountStore } from "@/stores/account";
import { useAliasStore } from "@/stores/alias";
import type { Alias } from "@/api/types";
import { copyText, formatTime, sessionStateText, sessionStateType } from "@/utils/format";

const route = useRoute();
const store = useAccountStore();
const aliasStore = useAliasStore();

const accountId = ref<number | null>(null);
const createVisible = ref(false);
const creating = ref(false);
const domainsLoading = ref(false);
const createFormRef = ref<FormInstance>();
const createForm = reactive({ localPart: "", domain: "mail.com" });
const createRules: FormRules = {
  localPart: [
    { required: true, message: "请输入别名前缀", trigger: "blur" },
    { pattern: /^[a-z0-9._-]{3,62}$/, message: "3-62 位小写字母/数字/点/下划线/连字符", trigger: "blur" },
  ],
};

const senderVisible = ref(false);
const senderTarget = ref<Alias | null>(null);
const senderMode = ref<"email" | "name-email">("email");
const senderDisplayName = ref("");
const senderSaving = ref(false);

interface BatchResult {
  key: string;
  address: string;
  ok: boolean;
  pickupUrl?: string;
  message?: string;
}

const batchVisible = ref(false);
const batchRunning = ref(false);
const batchAccountMode = ref<"auto" | number>("auto");
const batchResults = ref<BatchResult[]>([]);
const batchCount = ref(10);
const batchDomain = ref("mail.com");
const batchPrefix = ref("");
const batchLength = ref(10);

const batchSuccessCount = computed(() => batchResults.value.filter((item) => item.ok).length);
const batchOutput = computed(() =>
  batchResults.value
    .filter((item) => item.ok && item.pickupUrl)
    .map((item) => `${item.address}----${item.pickupUrl}`)
    .join("\n"),
);
const hasAnyAccount = computed(() =>
  store.accounts.some((account) => account.alias_count < account.alias_limit),
);

/** 按选择范围计算剩余可创建数量 */
const remainingCapacity = computed(() => {
  const scope =
    batchAccountMode.value === "auto"
      ? store.accounts
      : store.accounts.filter((account) => account.id === batchAccountMode.value);
  return scope.reduce((sum, account) => sum + Math.max(0, account.alias_limit - account.alias_count), 0);
});

/** 预览一个示例地址 */
const previewAddress = computed(() => {
  const rand = "kx7fq2m9z0".slice(0, Math.max(1, batchLength.value - batchPrefix.value.length));
  return `${batchPrefix.value}${rand}@${batchDomain.value}`;
});

function onPrefixInput(value: string): void {
  batchPrefix.value = value.toLowerCase().replace(/[^a-z0-9._-]/g, "");
}

const currentAccount = computed(() => store.accounts.find((account) => account.id === accountId.value) ?? null);
const canCreate = computed(
  () => Boolean(currentAccount.value) && currentAccount.value!.alias_count < currentAccount.value!.alias_limit,
);
const fullAddress = computed(() =>
  createForm.localPart && createForm.domain ? `${createForm.localPart}@${createForm.domain}` : "",
);

const usagePercent = computed(() => {
  if (!currentAccount.value?.alias_limit) return 0;
  return Math.min(
    Math.round((currentAccount.value.alias_count / currentAccount.value.alias_limit) * 100),
    100,
  );
});

const isFull = computed(() => {
  const account = currentAccount.value;
  return Boolean(account) && account!.alias_count >= account!.alias_limit;
});

function rowClassName({ row }: { row: Alias }): string {
  return row.id === aliasStore.lastCreatedId ? "row-highlight" : "";
}

/* ---------- 批量删除 ---------- */
const tableRef = ref<{ clearSelection: () => void; toggleAllSelection: () => void }>();
const selectedIds = ref<number[]>([]);
const batchDeleting = ref(false);

/** 只有可删除的别名才能被勾选 */
function isSelectable(row: Alias): boolean {
  return row.deletable;
}

/** 当前列表中可删除的别名数量 */
const deletableCount = computed(() => aliasStore.aliases.filter((alias) => alias.deletable).length);

/** 一键勾选全部可删除的别名（再次点击取消） */
function selectAllDeletable(): void {
  if (selectedIds.value.length > 0) {
    tableRef.value?.clearSelection();
    selectedIds.value = [];
    return;
  }
  tableRef.value?.toggleAllSelection();
}

function onSelectionChange(rows: Alias[]): void {
  selectedIds.value = rows.map((row) => row.id);
}

function clearSelection(): void {
  tableRef.value?.clearSelection();
  selectedIds.value = [];
}

async function handleBatchDelete(): Promise<void> {
  const ids = selectedIds.value;
  if (ids.length === 0) return;

  const deletableCount = aliasStore.aliases.filter(
    (alias) => ids.includes(alias.id) && alias.deletable,
  ).length;
  await ElMessageBox.confirm(`确定删除选中的 ${deletableCount} 个别名吗？此操作不可撤销。`, "警告", {
    type: "warning",
  });

  batchDeleting.value = true;
  try {
    const result = await aliasStore.removeMany(ids);
    if (result.failed > 0) {
      ElMessage.warning(`删除完成：成功 ${result.deleted}，失败 ${result.failed}`);
    } else {
      ElMessage.success(`已删除 ${result.deleted} 个别名`);
    }
    clearSelection();
    await Promise.all([loadAliases(), store.fetchAll()]);
  } finally {
    batchDeleting.value = false;
  }
}

function onLocalPartInput(value: string): void {
  createForm.localPart = value.toLowerCase();
}

async function onAccountChange(id: number): Promise<void> {
  store.select(id);
  await Promise.all([loadAliases(), loadDomains()]);
}

async function loadAliases(): Promise<void> {
  if (!accountId.value) return;
  await aliasStore.fetchByAccount(accountId.value);
}

async function loadDomains(): Promise<void> {
  if (!accountId.value) return;
  domainsLoading.value = true;
  try {
    await aliasStore.fetchDomains(accountId.value);
    if (aliasStore.domains.length > 0 && !aliasStore.domains.includes(createForm.domain)) {
      createForm.domain = aliasStore.domains[0]!;
    }
  } finally {
    domainsLoading.value = false;
  }
}

async function openCreate(): Promise<void> {
  createForm.localPart = "";
  createVisible.value = true;
  await loadDomains();
}

async function handleCreate(): Promise<void> {
  const valid = await createFormRef.value?.validate().catch(() => false);
  if (!valid || !accountId.value) return;
  creating.value = true;
  try {
    const alias = await aliasStore.create(accountId.value, fullAddress.value);
    ElMessage.success(`创建成功，取件地址：${alias.pickup_url}`);
    createVisible.value = false;
    await store.fetchAll();
  } finally {
    creating.value = false;
  }
}

async function copyPickup(row: Alias): Promise<void> {
  const ok = await copyText(row.pickup_url);
  if (ok) ElMessage.success("取件地址已复制");
}

/** 全部别名按 `别名邮箱----取件地址` 格式导出 */
const aliasExportText = computed(() =>
  aliasStore.aliases.map((alias) => `${alias.address}----${alias.pickup_url}`).join("\n"),
);

async function copyAllAliases(): Promise<void> {
  if (!aliasExportText.value) {
    ElMessage.warning("没有可复制的别名");
    return;
  }
  const ok = await copyText(aliasExportText.value);
  if (ok) {
    ElMessage.success(`已复制 ${aliasStore.aliases.length} 条（格式：别名----取件地址）`);
  }
}

/**
 * 打开批量生成对话框，并确保域名列表已加载。
 */
async function openBatch(): Promise<void> {
  batchAccountMode.value = "auto";
  batchResults.value = [];
  batchVisible.value = true;
  if (aliasStore.domains.length === 0) {
    await refreshDomains();
  }
  if (aliasStore.domains.length > 0 && !aliasStore.domains.includes(batchDomain.value)) {
    batchDomain.value = aliasStore.domains[0]!;
  }
}

function resetBatch(): void {
  batchResults.value = [];
  batchAccountMode.value = "auto";
}

/** 强制回源刷新域名（不走本地缓存） */
async function refreshDomains(): Promise<void> {
  if (!accountId.value) return;
  domainsLoading.value = true;
  try {
    await aliasStore.fetchDomains(accountId.value, true);
    ElMessage.success(`已更新域名列表（${aliasStore.domains.length} 个）`);
  } finally {
    domainsLoading.value = false;
  }
}

async function handleBatchGenerate(): Promise<void> {
  if (batchCount.value < 1) {
    ElMessage.warning("请填写生成数量");
    return;
  }
  batchRunning.value = true;
  batchResults.value = [];
  const accountId = batchAccountMode.value === "auto" ? null : batchAccountMode.value;

  try {
    const result = await aliasStore.batchGenerate({
      count: batchCount.value,
      domain: batchDomain.value,
      accountId,
      prefix: batchPrefix.value,
      length: batchLength.value,
    });
    batchResults.value = result.items.map((item) => ({
      key: item.address,
      address: item.address,
      ok: item.ok,
      pickupUrl: item.alias?.pickup_url,
      message: item.error?.message,
    }));
    if (result.failed > 0) {
      ElMessage.warning(`生成完成：成功 ${result.created}，失败 ${result.failed}`);
    } else {
      ElMessage.success(`生成完成：成功创建 ${result.created} 个别名`);
    }
    await store.fetchAll();
    await loadAliases();
  } finally {
    batchRunning.value = false;
  }
}

async function copyBatchOutput(): Promise<void> {
  if (!batchOutput.value) {
    ElMessage.warning("没有可复制的结果");
    return;
  }
  const ok = await copyText(batchOutput.value);
  if (ok) ElMessage.success("已复制（格式：别名----取件地址）");
}

function downloadBatchOutput(): void {
  if (!batchOutput.value) {
    ElMessage.warning("没有可下载的结果");
    return;
  }
  const blob = new Blob([batchOutput.value], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `aliases_${Date.now()}.txt`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function openSender(row: Alias): void {
  senderTarget.value = row;
  senderDisplayName.value = row.display_name ?? "";
  senderMode.value = "email";
  senderVisible.value = true;
}

async function saveDisplayName(): Promise<void> {
  if (!senderTarget.value) return;
  const target = senderTarget.value;
  if ((target.display_name ?? "") === senderDisplayName.value) return;
  const updated = await aliasApiSetDisplayName(target.id, senderDisplayName.value);
  if (updated.display_name === null || updated.display_name === "") {
    senderMode.value = "email";
  }
}

async function aliasApiSetDisplayName(id: number, name: string): Promise<Alias> {
  await aliasStore.setDisplayName(id, name);
  const updated = aliasStore.aliases.find((alias) => alias.id === id);
  return updated ?? senderTarget.value!;
}

async function handleSenderSave(): Promise<void> {
  if (!senderTarget.value) return;
  senderSaving.value = true;
  try {
    await aliasStore.setDefaultSender(senderTarget.value.id, senderMode.value);
    ElMessage.success("默认发件人已更新");
    senderVisible.value = false;
  } finally {
    senderSaving.value = false;
  }
}

async function handleDelete(row: Alias): Promise<void> {
  await ElMessageBox.confirm(`确定删除别名 ${row.address} 吗？`, "警告", { type: "warning" });
  await aliasStore.remove(row.id);
  ElMessage.success("已删除");
  await store.fetchAll();
}

onMounted(async () => {
  await store.fetchAll();
  const queryId = Number(route.query.account);
  accountId.value = queryId || store.currentAccountId || store.accounts[0]?.id || null;
  if (accountId.value) {
    store.select(accountId.value);
    await Promise.all([loadAliases(), loadDomains()]);
  }
});
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

/* ---------- 账号摘要条 ---------- */
.summary-card :deep(.el-card__body) {
  padding: 18px 24px;
}

.account-summary {
  display: flex;
  align-items: center;
  gap: 24px;
  flex-wrap: wrap;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.summary-divider {
  width: 1px;
  align-self: stretch;
  min-height: 34px;
  background: var(--border-soft);
}

.summary-label {
  font-size: 11.5px;
  color: var(--text-faint);
  letter-spacing: 0.03em;
}

.summary-main {
  font-size: 13px;
  color: var(--text-primary);
}

.usage-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.usage-bar {
  width: 130px;
}

.usage-num {
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.usage-num.full {
  color: var(--danger);
  font-weight: 600;
}

.alias-input {
  width: 100%;
}

/* ---------- 批量操作条 ---------- */
.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  margin-bottom: 12px;
  background: rgba(64, 158, 255, 0.08);
  border: 1px solid rgba(64, 158, 255, 0.22);
  border-radius: 6px;
}

.batch-bar-text {
  font-size: 13px;
  color: var(--brand);
  font-weight: 600;
  margin-right: auto;
}

.time-cell {
  font-size: 12.5px;
}

/* ---------- 批量生成 ---------- */
.gen-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.gen-hint {
  font-size: 12px;
}

.batch-summary {
  display: flex;
  gap: 8px;
}

.invalid-lines {
  font-size: 12px;
  color: var(--danger);
  word-break: break-all;
}

.batch-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.batch-stat {
  font-size: 12px;
  margin-left: auto;
}

.batch-list {
  margin-top: 12px;
  max-height: 180px;
  overflow-y: auto;
}

.batch-result-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
  min-width: 0;
}

.result-msg {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-msg.error {
  color: var(--danger);
}

.mb-12 {
  margin-bottom: 12px;
}

@media (max-width: 760px) {
  .summary-divider {
    display: none;
  }

  .account-summary {
    gap: 16px;
  }
}
</style>
