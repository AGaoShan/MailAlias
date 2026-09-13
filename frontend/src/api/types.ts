export interface User {
  id: number;
  username: string;
  role: string;
  created_at?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

/** 账号登录状态，与后端 session_state 常量一致 */
export type SessionState = "unknown" | "logging_in" | "active" | "expired" | "error" | "none";

export interface Account {
  id: number;
  account_key: string;
  email: string;
  enabled: boolean;
  alias_count: number;
  alias_limit: number;
  session_state: SessionState;
  session_state_text: string;
  created_at: string;
  updated_at: string;
}

export interface AccountExportItem {
  email: string;
  password: string;
  session_state: SessionState;
  alias_count: number;
}

export interface AccountExportResponse {
  total: number;
  items: AccountExportItem[];
}

export interface Alias {
  id: number;
  account_id: number;
  account_email: string;
  address: string;
  local_part: string;
  domain: string;
  display_name: string | null;
  is_default_sender: boolean;
  deletable: boolean;
  state: string;
  pickup_url: string;
  created_at: string;
  last_fetched_at: string | null;
}

export interface AliasBatchItem {
  address: string;
  ok: boolean;
  alias: Alias | null;
  error: { code: string; message: string } | null;
}

export interface AliasBatchResult {
  requested: number;
  created: number;
  failed: number;
  items: AliasBatchItem[];
}

export interface AliasDeleteItem {
  alias_id: number;
  address: string;
  ok: boolean;
  error: { code: string; message: string } | null;
}

export interface AliasDeleteResult {
  requested: number;
  deleted: number;
  failed: number;
  items: AliasDeleteItem[];
}

export interface Mapping {
  alias_id: number;
  account_id: number;
  account_email: string;
  alias_address: string;
  pickup_url: string;
  is_default_sender: boolean;
  last_fetched_at: string | null;
}

export interface MappingListResponse {
  total: number;
  items: Mapping[];
}

export interface Message {
  id: string;
  from: string;
  to: string[];
  subject: string;
  date: string;
  preview: string;
  read: boolean;
  has_attachments: boolean;
  folder: string;
  code: string | null;
}

export interface PickupResponse {
  pickup_url: string;
  alias: string;
  account_key: string;
  messages: Message[];
  total: number;
  stale: boolean;
  fetched_at: string;
}

export interface PickupBatchItem {
  pickup_url: string;
  alias: string | null;
  ok: boolean;
  messages: Message[];
  error: { code: string; message: string } | null;
}

export interface PickupResolve {
  account_key: string;
  alias: string;
  account_id: number;
  account_email: string;
  alias_id: number;
}

export interface VerifyResponse {
  account_id: number;
  session_state: SessionState;
  ok: boolean;
}

export interface DomainsResponse {
  account_id: number;
  domains: string[];
}

export interface RecentFetch {
  pickup_url: string;
  alias: string;
  message_count: number;
  fetched_at: string;
}

export interface DashboardStats {
  account_count: number;
  alias_count: number;
  mapping_count: number;
  alias_capacity: { used: number; limit: number };
  recent_fetches: RecentFetch[];
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  extra?: Record<string, unknown>;
}

/** 已知后端错误码（用于前端提示与跳转判断） */
export type ApiErrorCode =
  | "UNAUTHORIZED"
  | "ACCOUNT_SESSION_INVALID"
  | "INVALID_CREDENTIALS"
  | "ALIAS_LIMIT_REACHED"
  | "ALIAS_EXISTS"
  | "DOMAIN_UNAVAILABLE"
  | "ALIAS_NOT_DELETABLE"
  | "UPSTREAM_ERROR"
  | "UPSTREAM_TIMEOUT"
  | "CIRCUIT_OPEN"
  | "RATE_LIMITED"
  | "NOT_FOUND"
  | "VALIDATION_ERROR";
