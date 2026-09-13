<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">映射列表</h2>
        <p class="page-subtitle">别名邮箱地址与取件地址的对应关系</p>
      </div>
      <div class="toolbar">
        <el-select v-model="filterAccountId" placeholder="全部账号" clearable style="width: 220px" @change="load">
          <el-option
            v-for="account in store.accounts"
            :key="account.id"
            :label="account.email"
            :value="account.id"
          />
        </el-select>
        <el-button :loading="loading" @click="load">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
        <el-button @click="copyAll">复制全部</el-button>
        <el-button type="primary" @click="exportFile('csv')">
          <el-icon><Download /></el-icon>导出 CSV
        </el-button>
        <el-button @click="exportFile('text')">导出文本</el-button>
      </div>
    </div>

    <el-card>
      <template #header>
        <div class="card-header">
          <span>共 <b class="total-num">{{ total }}</b> 条映射</span>
          <span class="text-muted format-hint">格式：alias ---- pickup_url</span>
        </div>
      </template>
      <el-table :data="items" v-loading="loading" empty-text="暂无映射，请先创建别名">
        <el-table-column prop="alias_address" label="别名邮箱地址" min-width="200">
          <template #default="{ row }">
            <span class="mono">{{ row.alias_address }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" align="center">
          <template #default>
            <span class="dash">----</span>
          </template>
        </el-table-column>
        <el-table-column prop="pickup_url" label="取件地址" min-width="300" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.pickup_url }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="account_email" label="所属账号" width="180">
          <template #default="{ row }">
            <span class="text-muted account-cell">{{ row.account_email }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="248" align="right">
          <template #default="{ row }">
            <el-button size="small" plain @click="copy(row.pickup_url)">复制取件地址</el-button>
            <el-button size="small" plain @click="copy(`${row.alias_address}----${row.pickup_url}`)">复制行</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { mappingApi } from "@/api";
import { useAccountStore } from "@/stores/account";
import type { Mapping } from "@/api/types";
import { copyText } from "@/utils/format";

const store = useAccountStore();
const items = ref<Mapping[]>([]);
const total = ref(0);
const loading = ref(false);
const filterAccountId = ref<number | null>(null);

async function load(): Promise<void> {
  loading.value = true;
  try {
    const result = await mappingApi.list(filterAccountId.value ?? undefined);
    items.value = result.items;
    total.value = result.total;
  } finally {
    loading.value = false;
  }
}

async function copy(text: string): Promise<void> {
  const ok = await copyText(text);
  if (ok) ElMessage.success("已复制");
}

async function copyAll(): Promise<void> {
  if (items.value.length === 0) {
    ElMessage.warning("没有可复制的内容");
    return;
  }
  const text = items.value.map((item) => `${item.alias_address}----${item.pickup_url}`).join("\n");
  await copy(text);
}

function exportFile(format: "text" | "csv"): void {
  const url = mappingApi.exportUrl(format);
  const signed = url;
  const link = document.createElement("a");
  link.href = signed;
  link.download = format === "csv" ? "mailcom_mappings.csv" : "mailcom_mappings.txt";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

onMounted(async () => {
  await store.fetchAll();
  await load();
});
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}

.total-num {
  font-weight: 650;
  color: var(--brand-600);
  font-variant-numeric: tabular-nums;
}

.format-hint {
  font-family: var(--font-mono);
  font-size: 11.5px;
}

.dash {
  color: var(--text-faint);
  font-family: var(--font-mono);
  font-size: 12px;
  user-select: none;
}

.account-cell {
  font-size: 12.5px;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
