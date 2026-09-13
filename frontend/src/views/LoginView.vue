<template>
  <div class="login-page">
    <div class="glow glow-a" />
    <div class="glow glow-b" />

    <div class="login-card">
      <div class="login-header">
        <span class="logo-mark"><el-icon :size="20"><Message /></el-icon></span>
        <h2>mail.com 别名管理</h2>
        <p>多账号 · 别名 · 取件地址统一管理</p>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" size="large" @submit.prevent="handleLogin">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            show-password
            :prefix-icon="Lock"
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="handleLogin">
          登 录
        </el-button>
      </el-form>

      <div class="login-foot">凭据加密存储 · 仅本地部署使用</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { Lock, User } from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();

const formRef = ref<FormInstance>();
const loading = ref(false);
const form = reactive({ username: "", password: "" });
const rules: FormRules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
};

async function handleLogin(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  loading.value = true;
  try {
    await auth.login(form.username, form.password);
    ElMessage.success("登录成功");
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/dashboard";
    router.push(redirect);
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background: linear-gradient(170deg, #fbfdfe 0%, #f2f8f8 55%, #eef7f5 100%);
}

/* 背景柔光斑 */
.glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  pointer-events: none;
}

.glow-a {
  width: 420px;
  height: 420px;
  top: -140px;
  right: -80px;
  background: rgba(85, 200, 176, 0.22);
}

.glow-b {
  width: 360px;
  height: 360px;
  bottom: -150px;
  left: -100px;
  background: rgba(142, 220, 201, 0.24);
}

.login-card {
  position: relative;
  width: 396px;
  padding: 40px 36px 32px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: 0 18px 50px rgba(28, 43, 51, 0.08), 0 2px 8px rgba(28, 43, 51, 0.03);
  animation: card-in 0.45s cubic-bezier(0.23, 1, 0.32, 1);
}

@keyframes card-in {
  from {
    opacity: 0;
    transform: translateY(14px) scale(0.99);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.login-header {
  text-align: center;
  margin-bottom: 28px;
}

.logo-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 46px;
  border-radius: 14px;
  color: #fff;
  background: linear-gradient(140deg, var(--brand-400), var(--brand-600));
  box-shadow: 0 6px 18px rgba(47, 174, 149, 0.3);
  margin-bottom: 16px;
}

.login-header h2 {
  margin: 0 0 6px;
  font-size: 19px;
  font-weight: 650;
  letter-spacing: -0.02em;
}

.login-header p {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-muted);
}

.login-btn {
  width: 100%;
  margin-top: 6px;
  height: 44px;
  border-radius: 10px;
  font-size: 15px;
  letter-spacing: 0.12em;
}

.login-foot {
  margin-top: 24px;
  text-align: center;
  font-size: 11.5px;
  color: var(--text-faint);
}

@media (max-width: 480px) {
  .login-card {
    width: 100%;
    margin: 0 20px;
    padding: 32px 24px 26px;
  }
}
</style>
