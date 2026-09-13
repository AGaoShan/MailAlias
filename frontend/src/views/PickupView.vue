<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">取件查看</h2>
        <p class="page-subtitle">按取件地址拉取邮件并在线阅读</p>
      </div>
    </div>

    <el-card class="mb-16 filter-card">
      <el-form :inline="true" class="pickup-form">
        <el-form-item label="选择别名">
          <el-select
            v-model="selectedMappingKey"
            placeholder="从映射中选择"
            style="width: 300px"
            clearable
            filterable
            @change="onSelectMapping"
          >
            <el-option
              v-for="item in mappings"
              :key="item.alias_id"
              :label="`${item.alias_address} (${item.account_email})`"
              :value="String(item.alias_id)"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="取件地址">
          <el-input v-model="pickupUrl" placeholder="http://host/api/v1/pickup/acc_xxx/alias@mail.com" style="width: 380px" />
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="amount" :min="1" :max="100" controls-position="right" />
        </el-form-item>
        <el-form-item class="check-item">
          <el-checkbox v-model="unreadOnly">仅未读</el-checkbox>
          <el-checkbox v-model="markRead">标记已读</el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" :disabled="!pickupUrl" @click="fetchMessages(true)">
            <el-icon><Download /></el-icon>取件
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-alert
      v-if="result?.stale"
      type="warning"
      :closable="false"
      title="上游服务不可用，当前展示最近一次缓存结果（stale）"
      class="mb-16"
    />

    <div class="mail-grid">
      <el-card class="mail-list-card">
        <template #header>
          <div class="card-header">
            <span>邮件列表 <b class="count-badge">{{ result?.messages.length ?? 0 }}</b></span>
            <span v-if="result" class="text-muted mono alias-hint">{{ result.alias }}</span>
          </div>
        </template>
        <el-empty v-if="!result" description="请先选择别名或输入取件地址后取件" />
        <el-empty v-else-if="result.messages.length === 0" description="暂无邮件" />
        <div v-else class="message-list">
          <div
            v-for="message in result.messages"
            :key="message.id"
            class="message-item"
            :class="{ active: activeMessage?.id === message.id, unread: !message.read }"
            @click="openMessage(message)"
          >
            <div class="message-top">
              <span class="message-subject">{{ message.subject || "(无主题)" }}</span>
              <span class="message-date">{{ formatTime(message.date) }}</span>
            </div>
            <div class="message-from mono">{{ message.from }}</div>
            <div v-if="message.code" class="message-code">
              <span class="code-label">验证码</span>
              <span class="code-value mono">{{ message.code }}</span>
              <span class="code-copy" @click.stop="copyCode(message.code)">复制</span>
            </div>
            <div class="message-preview text-muted">{{ message.preview }}</div>
            <div class="message-tags">
              <span class="mini-tag">{{ message.folder }}</span>
              <span v-if="!message.read" class="mini-tag danger">未读</span>
              <span v-if="message.has_attachments" class="mini-tag warn">附件</span>
            </div>
          </div>
        </div>
      </el-card>

      <el-card class="mail-body-card">
        <template #header>
          <div class="card-header">
            <span>邮件正文</span>
            <el-radio-group v-if="activeMessage" v-model="bodyFormat" size="small" @change="loadBody">
              <el-radio-button value="html">HTML</el-radio-button>
              <el-radio-button value="text">纯文本</el-radio-button>
            </el-radio-group>
          </div>
        </template>
        <el-empty v-if="!activeMessage" description="点击左侧邮件查看正文" />
        <div v-else class="body-wrap">
          <h3 class="body-subject">{{ activeMessage.subject || "(无主题)" }}</h3>
          <div v-if="activeMessage.code" class="body-code">
            <span class="code-label">验证码</span>
            <span class="code-value mono">{{ activeMessage.code }}</span>
            <el-button size="small" type="primary" plain @click="copyCode(activeMessage.code)">
              复制验证码
            </el-button>
          </div>
          <div class="body-meta">
            <div class="meta-row"><span class="meta-key">发件人</span><span class="mono">{{ activeMessage.from }}</span></div>
            <div class="meta-row"><span class="meta-key">收件人</span><span class="mono">{{ activeMessage.to.join(", ") }}</span></div>
            <div class="meta-row"><span class="meta-key">时间</span><span>{{ formatTime(activeMessage.date) }}</span></div>
          </div>
          <el-divider />
          <div v-if="bodyLoading" v-loading="true" class="body-loading" />
          <iframe
            v-else-if="bodyFormat === 'html'"
            class="body-frame"
            :srcdoc="bodyContent"
            sandbox=""
          />
          <pre v-else class="body-text">{{ bodyContent }}</pre>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { mappingApi } from "@/api";
import { pickupApi } from "@/api/pickup";
import type { Mapping, Message, PickupResponse } from "@/api/types";
import { copyText, formatTime } from "@/utils/format";

const mappings = ref<Mapping[]>([]);
const selectedMappingKey = ref<string | null>(null);
const pickupUrl = ref("");
const amount = ref(25);
const unreadOnly = ref(false);
const markRead = ref(false);
const loading = ref(false);
const result = ref<PickupResponse | null>(null);
const activeMessage = ref<Message | null>(null);
const bodyContent = ref("");
const bodyFormat = ref<"html" | "text">("html");
const bodyLoading = ref(false);

async function loadMappings(): Promise<void> {
  const data = await mappingApi.list();
  mappings.value = data.items;
}

function onSelectMapping(value: string): void {
  if (!value) return;
  const mapping = mappings.value.find((item) => item.alias_id === Number(value));
  if (mapping) pickupUrl.value = mapping.pickup_url;
}

async function fetchMessages(showMessage = false): Promise<void> {
  if (!pickupUrl.value) return;
  loading.value = true;
  try {
    const resolved = await pickupApi.resolve(pickupUrl.value).catch(() => null);
    if (!resolved) {
      ElMessage.error("取件地址无效");
      return;
    }
    result.value = await pickupApi.fetch(resolved.account_key, resolved.alias, {
      amount: amount.value,
      unreadOnly: unreadOnly.value,
      markRead: markRead.value,
      refresh: true,
    });
    activeMessage.value = null;
    bodyContent.value = "";
    if (showMessage) ElMessage.success(`取到 ${result.value.messages.length} 封邮件`);
  } finally {
    loading.value = false;
  }
}

async function loadBody(): Promise<void> {
  if (!activeMessage.value || !result.value) return;
  const address = result.value.alias;
  const accountKey = result.value.account_key;
  bodyLoading.value = true;
  try {
    bodyContent.value = await pickupApi.fetchBody(accountKey, address, activeMessage.value.id, bodyFormat.value);
  } finally {
    bodyLoading.value = false;
  }
}

async function openMessage(message: Message): Promise<void> {
  activeMessage.value = message;
  await loadBody();
}

async function copyCode(code: string | null): Promise<void> {
  if (!code) return;
  const ok = await copyText(code);
  if (ok) ElMessage.success(`已复制验证码：${code}`);
}

onMounted(async () => {
  await loadMappings();
});
</script>

<style scoped>
.filter-card :deep(.el-card__body) {
  padding: 18px 22px 4px;
}

.pickup-form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0 4px;
}

.pickup-form :deep(.el-form-item) {
  margin-bottom: 14px;
  margin-right: 14px;
}

.check-item :deep(.el-form-item__content) {
  gap: 16px;
}

/* ---------- 双栏邮件布局 ---------- */
.mail-grid {
  display: grid;
  grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
  gap: 16px;
  align-items: start;
}

.mail-list-card :deep(.el-card__body),
.mail-body-card :deep(.el-card__body) {
  padding: 0;
}

.mail-body-card :deep(.el-card__body) {
  padding: 0 22px 22px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.count-badge {
  display: inline-block;
  min-width: 26px;
  padding: 1px 8px;
  margin-left: 4px;
  border-radius: 999px;
  background: var(--brand-50);
  color: var(--brand-600);
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: center;
}

.alias-hint {
  font-size: 11.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 45%;
}

/* ---------- 邮件条目 ---------- */
.message-list {
  max-height: 660px;
  overflow-y: auto;
}

.message-item {
  padding: 13px 20px;
  border-bottom: 1px solid var(--border-soft);
  border-left: 3px solid transparent;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease;
}

.message-item:last-child {
  border-bottom: none;
}

.message-item:hover {
  background: var(--surface-sunken);
}

.message-item.active {
  background: var(--brand-50);
  border-left-color: var(--brand-500);
}

.message-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
}

.message-subject {
  font-size: 13.5px;
  color: var(--text-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message-item.unread .message-subject {
  font-weight: 650;
  color: var(--text-primary);
}

.message-date {
  font-size: 11.5px;
  color: var(--text-faint);
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.message-from {
  font-size: 11.5px;
  color: var(--text-regular);
  margin-top: 5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message-preview {
  font-size: 12px;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ---------- 验证码 ---------- */
.message-code {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  padding: 2px 10px;
  border-radius: 4px;
  background: rgba(64, 158, 255, 0.1);
  border: 1px solid rgba(64, 158, 255, 0.25);
}

.code-label {
  font-size: 11px;
  color: var(--text-faint);
}

.code-value {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--brand);
}

.code-copy {
  font-size: 11px;
  color: var(--brand);
  cursor: pointer;
  user-select: none;
}

.code-copy:hover {
  text-decoration: underline;
}

.body-code {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 14px;
  padding: 10px 14px;
  border-radius: 6px;
  background: rgba(64, 158, 255, 0.08);
  border: 1px solid rgba(64, 158, 255, 0.22);
}

.body-code .code-value {
  font-size: 20px;
}

.message-tags {
  margin-top: 8px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.mini-tag {
  font-size: 11px;
  line-height: 18px;
  padding: 0 8px;
  border-radius: 5px;
  background: #f2f6f7;
  color: var(--text-muted);
}

.mini-tag.danger {
  background: var(--danger-soft);
  color: var(--danger);
}

.mini-tag.warn {
  background: var(--warn-soft);
  color: var(--warn);
}

/* ---------- 正文 ---------- */
.body-wrap {
  padding-top: 20px;
}

.body-subject {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 650;
  letter-spacing: -0.01em;
  line-height: 1.5;
}

.body-meta {
  font-size: 12.5px;
  line-height: 1.6;
  display: grid;
  gap: 5px;
}

.meta-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
}

.meta-key {
  color: var(--text-faint);
  flex-shrink: 0;
  width: 42px;
}

.meta-row .mono {
  color: var(--text-regular);
}

.body-frame {
  width: 100%;
  height: 500px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fff;
}

.body-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--text-regular);
  background: var(--surface-sunken);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-sm);
  padding: 16px;
  margin: 0;
  max-height: 500px;
  overflow: auto;
}

.body-loading {
  height: 240px;
}

@media (max-width: 1080px) {
  .mail-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .message-list {
    max-height: 400px;
  }
}
</style>
