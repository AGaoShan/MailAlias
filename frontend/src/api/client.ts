import axios, { type AxiosError, type AxiosInstance } from "axios";
import { ElMessage } from "element-plus";
import type { ApiErrorDetail } from "./types";

const TOKEN_KEY = "mailcom_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

const client: AxiosInstance = axios.create({
  baseURL: "/api/v1",
  timeout: 120000,
});

client.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: ApiErrorDetail | string }>) => {
    const status = error.response?.status;
    const detail = error.response?.data?.detail;
    let message = error.message;
    let code = "UNKNOWN";

    if (detail && typeof detail === "object") {
      message = detail.message;
      code = detail.code;
    } else if (typeof detail === "string") {
      message = detail;
    }

    // 仅当“登录态本身失效”时才跳登录页；
    // mail.com 账号会话失效等业务 401（ACCOUNT_SESSION_INVALID）不在此列。
    const isAuthExpired =
      status === 401 && (code === "UNAUTHORIZED" || code === "UNKNOWN" || !detail);

    if (isAuthExpired) {
      clearToken();
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
      message = "登录已过期，请重新登录";
    } else if (!error.config?.silent) {
      ElMessage.error(message);
    }

    return Promise.reject({ code, message, status });
  },
);

export default client;
export type { AxiosError };
