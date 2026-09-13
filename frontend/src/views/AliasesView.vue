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
      <el-table
        :data="aliasStore.aliases"
        v-loading="aliasStore.loading"
        empty-text="暂无别名"
        :row-class-name="rowClassName"
      >
        <el-table-column prop="address" label="别名地址" min-width="200">
          <template #default="{ row }">
            <span class="mono">{{ row.address }}</span>
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
        <el-table-column label="可删除" width="95" align="center">
          <template #default="{ row }">
            <span class="text-muted">{{ row.deletable ? "是" : "否" }}</span>
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
import { copyText, sessionStateText, sessionStateType } from "@/utils/format";

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

@media (max-width: 760px) {
  .summary-divider {
    display: none;
  }

  .account-summary {
    gap: 16px;
  }
}
</style>
