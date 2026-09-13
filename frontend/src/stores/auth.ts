import { defineStore } from "pinia";
import { authApi } from "@/api";
import { clearToken, getToken, setToken } from "@/api/client";
import type { User } from "@/api/types";

interface AuthState {
  token: string | null;
  user: User | null;
  ready: boolean;
}

export const useAuthStore = defineStore("auth", {
  state: (): AuthState => ({
    token: getToken(),
    user: null,
    ready: false,
  }),

  getters: {
    isAuthenticated: (state): boolean => Boolean(state.token),
  },

  actions: {
    async login(username: string, password: string): Promise<void> {
      const result = await authApi.login(username, password);
      this.token = result.access_token;
      this.user = result.user;
      setToken(result.access_token);
      this.ready = true;
    },

    async loadUser(): Promise<void> {
      if (!this.token) {
        this.ready = true;
        return;
      }
      try {
        this.user = await authApi.me();
      } catch {
        this.token = null;
        this.user = null;
        clearToken();
      } finally {
        this.ready = true;
      }
    },

    async logout(): Promise<void> {
      try {
        await authApi.logout();
      } catch {
        // 忽略后端登出失败，前端幂等清理
      }
      this.token = null;
      this.user = null;
      clearToken();
    },
  },
});
