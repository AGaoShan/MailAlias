<template>
  <el-container class="layout">
    <el-aside width="228px" class="aside">
      <div class="logo">
        <span class="logo-mark">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <rect x="2.4" y="4.6" width="19.2" height="14.8" rx="3.1" fill="none" stroke="#ffffff" stroke-width="1.7" />
            <path d="M6.2 9.6 L12 13.3 L17.8 9.6" fill="none" stroke="#ffffff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
            <circle cx="18.4" cy="16.2" r="2.1" fill="#ffffff" />
          </svg>
        </span>
        <span class="logo-text">Mail<em>Alias</em></span>
      </div>

      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>

      <div class="aside-foot">
        <span class="dot" />
        <span>服务运行中</span>
      </div>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <h1 class="header-title">{{ currentTitle }}</h1>
          <span class="header-crumb">MailAlias · 多账号别名与取件</span>
        </div>
        <div class="header-right">
          <el-tag v-if="auth.user" class="user-chip" effect="plain" round>
            <el-icon :size="13"><User /></el-icon>
            {{ auth.user.username }}
          </el-tag>
          <el-button link class="logout" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            退出
          </el-button>
        </div>
      </el-header>

      <el-main class="main">
        <router-view v-slot="{ Component }">
          <keep-alive :include="[]">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, markRaw } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessageBox } from "element-plus";
import {
  Connection,
  Download,
  Odometer,
  PriceTag,
  User,
} from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const menus = markRaw([
  { path: "/dashboard", label: "仪表盘", icon: Odometer },
  { path: "/accounts", label: "账号管理", icon: User },
  { path: "/aliases", label: "别名管理", icon: PriceTag },
  { path: "/mappings", label: "映射列表", icon: Connection },
  { path: "/pickup", label: "取件查看", icon: Download },
]);

const titles: Record<string, string> = {
  dashboard: "仪表盘",
  accounts: "账号管理",
  aliases: "别名管理",
  mappings: "映射列表",
  pickup: "取件查看",
};

const activeMenu = computed(() => route.path);
const currentTitle = computed(() => titles[String(route.name)] ?? "");

async function handleLogout(): Promise<void> {
  await ElMessageBox.confirm("确定要退出登录吗？", "提示", { type: "warning" });
  await auth.logout();
  router.push({ name: "login" });
}
</script>

<style scoped>
.layout {
  height: 100%;
}

/* ---------- 侧边栏 ---------- */
.aside {
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
}

.logo {
  height: 64px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 20px;
  flex-shrink: 0;
}

.logo-mark {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(140deg, var(--brand-400), var(--brand-600));
  box-shadow: 0 2px 8px rgba(47, 174, 149, 0.3);
  flex-shrink: 0;
}

.logo-text {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text-primary);
  white-space: nowrap;
}

.logo-text em {
  font-style: normal;
  font-weight: 400;
  color: var(--brand-600);
}

.menu {
  border-right: none;
  background: transparent;
  flex: 1;
  padding: 6px 12px;
}

.menu :deep(.el-menu-item) {
  height: 42px;
  line-height: 42px;
  border-radius: 9px;
  margin-bottom: 3px;
  padding-left: 12px !important;
  padding-right: 12px;
  color: var(--text-regular);
  font-size: 13.5px;
  border-bottom: none;
  transition: background 0.18s ease, color 0.18s ease;
}

.menu :deep(.el-menu-item .el-icon) {
  width: 18px;
  font-size: 16px;
  margin-right: 10px;
  color: var(--text-muted);
  transition: color 0.18s ease;
}

.menu :deep(.el-menu-item:hover) {
  background: var(--surface-sunken);
  color: var(--text-primary);
}

.menu :deep(.el-menu-item:hover .el-icon) {
  color: var(--text-regular);
}

.menu :deep(.el-menu-item.is-active) {
  background: var(--brand-50);
  color: var(--brand-600) !important;
  font-weight: 600;
}

.menu :deep(.el-menu-item.is-active .el-icon) {
  color: var(--brand-500);
}

.aside-foot {
  padding: 14px 20px;
  border-top: 1px solid var(--border-soft);
  font-size: 11.5px;
  color: var(--text-faint);
  display: flex;
  align-items: center;
  gap: 7px;
  flex-shrink: 0;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ok);
  box-shadow: 0 0 0 3px var(--ok-soft);
}

/* ---------- 顶栏 ---------- */
.header {
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
}

.header-title {
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
  margin: 0;
}

.header-crumb {
  font-size: 12px;
  color: var(--text-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 14px;
}

.user-chip {
  background: var(--surface-sunken);
  border-color: var(--border);
  color: var(--text-regular);
  font-size: 12.5px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.logout {
  color: var(--text-muted);
  font-size: 13px;
}

.logout:hover {
  color: var(--danger);
}

/* ---------- 内容区 ---------- */
.main {
  background: var(--page-bg);
  padding: 0;
  overflow-y: auto;
}

@media (max-width: 900px) {
  .aside {
    width: 68px !important;
  }

  .logo-text,
  .menu :deep(.el-menu-item span),
  .aside-foot {
    display: none;
  }

  .menu :deep(.el-menu-item) {
    justify-content: center;
    padding-left: 0 !important;
  }

  .menu :deep(.el-menu-item .el-icon) {
    margin-right: 0;
  }

  .header-crumb {
    display: none;
  }
}
</style>
