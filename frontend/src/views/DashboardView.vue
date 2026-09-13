<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">仪表盘</h2>
        <p class="page-subtitle">账号、别名与取件状态的实时概览</p>
      </div>
      <el-button :loading="loading" @click="load">
        <el-icon><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <div class="stat-grid mb-16">
      <div v-for="card in cards" :key="card.label" class="stat-card" :class="`tone-${card.tone}`">
        <div class="stat-icon">
          <el-icon :size="20"><component :is="card.icon" /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value">{{ card.value }}</div>
        </div>
      </div>
    </div>

    <el-card class="recent-card">
      <template #header>
        <div class="card-head">
          <span>最近取件</span>
          <span class="text-muted hint">最新 {{ stats?.recent_fetches?.length ?? 0 }} 条</span>
        </div>
      </template>
      <el-table :data="stats?.recent_fetches ?? []" v-loading="loading" empty-text="暂无取件记录">
        <el-table-column prop="alias" label="别名" min-width="220">
          <template #default="{ row }">
            <span class="mono">{{ row.alias }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="pickup_url" label="取件地址" min-width="320" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono text-muted">{{ row.pickup_url }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="message_count" label="邮件数" width="100" align="right">
          <template #default="{ row }">
            <span class="count-pill">{{ row.message_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="fetched_at" label="取件时间" width="200">
          <template #default="{ row }">
            <span class="text-muted">{{ formatTime(row.fetched_at) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Connection, DataLine, PriceTag, User } from "@element-plus/icons-vue";
import { dashboardApi } from "@/api";
import type { DashboardStats } from "@/api/types";
import { formatTime } from "@/utils/format";

const stats = ref<DashboardStats | null>(null);
const loading = ref(false);

const cards = computed(() => [
  {
    label: "账号总数",
    value: String(stats.value?.account_count ?? 0),
    icon: User,
    tone: "brand",
  },
  {
    label: "别名总数",
    value: String(stats.value?.alias_count ?? 0),
    icon: PriceTag,
    tone: "green",
  },
  {
    label: "取件映射",
    value: String(stats.value?.mapping_count ?? 0),
    icon: Connection,
    tone: "amber",
  },
  {
    label: "别名容量",
    value: `${stats.value?.alias_capacity.used ?? 0} / ${stats.value?.alias_capacity.limit ?? 0}`,
    icon: DataLine,
    tone: "violet",
  },
]);

async function load(): Promise<void> {
  loading.value = true;
  try {
    stats.value = await dashboardApi.stats();
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 20px 22px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.24s ease, transform 0.24s ease, border-color 0.24s ease;
}

.stat-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
  border-color: #dce8eb;
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.tone-brand .stat-icon {
  background: var(--brand-50);
  color: var(--brand-500);
}

.tone-green .stat-icon {
  background: var(--ok-soft);
  color: var(--ok);
}

.tone-amber .stat-icon {
  background: var(--warn-soft);
  color: var(--warn);
}

.tone-violet .stat-icon {
  background: #f3f1fd;
  color: #7d6fd0;
}

.stat-body {
  min-width: 0;
}

.stat-label {
  font-size: 12.5px;
  color: var(--text-muted);
  letter-spacing: 0.01em;
}

.stat-value {
  font-size: 25px;
  font-weight: 650;
  letter-spacing: -0.03em;
  line-height: 1.25;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.hint {
  font-size: 12px;
  font-weight: 400;
}

.count-pill {
  display: inline-block;
  min-width: 34px;
  padding: 1px 9px;
  border-radius: 999px;
  background: var(--surface-sunken);
  color: var(--text-regular);
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
  text-align: center;
}

@media (max-width: 1180px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .stat-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
