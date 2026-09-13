import client from "./client";
import type {
  Account,
  Alias,
  AliasBatchResult,
  DashboardStats,
  DomainsResponse,
  LoginResponse,
  MappingListResponse,
  User,
  VerifyResponse,
} from "./types";

export const authApi = {
  async login(username: string, password: string): Promise<LoginResponse> {
    const { data } = await client.post<LoginResponse>("/auth/login", { username, password });
    return data;
  },
  async me(): Promise<User> {
    const { data } = await client.get<User>("/auth/me");
    return data;
  },
  async logout(): Promise<void> {
    await client.post("/auth/logout");
  },
};

export const accountApi = {
  async list(): Promise<Account[]> {
    const { data } = await client.get<Account[]>("/accounts");
    return data;
  },
  async create(email: string, password: string, silent = false): Promise<Account> {
    const { data } = await client.post<Account>("/accounts", { email, password }, { silent });
    return data;
  },
  async remove(id: number): Promise<void> {
    await client.delete(`/accounts/${id}`);
  },
  async verify(id: number): Promise<VerifyResponse> {
    const { data } = await client.post<VerifyResponse>(`/accounts/${id}/verify`);
    return data;
  },
};

export const aliasApi = {
  async listByAccount(accountId: number): Promise<Alias[]> {
    const { data } = await client.get<Alias[]>(`/accounts/${accountId}/aliases`);
    return data;
  },
  async create(accountId: number, address: string): Promise<Alias> {
    const { data } = await client.post<Alias>(`/accounts/${accountId}/aliases`, { address });
    return data;
  },
  async createAuto(address: string, accountId?: number | null, silent = false): Promise<Alias> {
    const { data } = await client.post<Alias>(
      "/aliases",
      { address, account_id: accountId ?? null },
      { silent },
    );
    return data;
  },
  async remove(id: number): Promise<void> {
    await client.delete(`/aliases/${id}`);
  },
  async setDefaultSender(id: number, sender: "email" | "name-email"): Promise<Alias> {
    const { data } = await client.put<Alias>(`/aliases/${id}/default-sender`, { sender });
    return data;
  },
  async setDisplayName(id: number, displayName: string): Promise<Alias> {
    const { data } = await client.put<Alias>(`/aliases/${id}/display-name`, { display_name: displayName });
    return data;
  },
  async domains(accountId: number, refresh = false): Promise<DomainsResponse> {
    const { data } = await client.get<DomainsResponse>(`/accounts/${accountId}/domains`, {
      params: refresh ? { refresh: true } : undefined,
    });
    return data;
  },
  async batchGenerate(options: {
    count: number;
    domain: string;
    accountId?: number | null;
    prefix?: string;
    length?: number;
  }): Promise<AliasBatchResult> {
    const { data } = await client.post<AliasBatchResult>("/aliases/batch-generate", {
      count: options.count,
      domain: options.domain,
      account_id: options.accountId ?? null,
      prefix: options.prefix ?? "",
      length: options.length ?? 10,
    });
    return data;
  },
};

export const mappingApi = {
  async list(accountId?: number): Promise<MappingListResponse> {
    const { data } = await client.get<MappingListResponse>("/mappings", {
      params: accountId ? { account_id: accountId } : undefined,
    });
    return data;
  },
  exportUrl(format: "text" | "csv"): string {
    return `/api/v1/mappings/export?format=${format}`;
  },
};

export const dashboardApi = {
  async stats(): Promise<DashboardStats> {
    const { data } = await client.get<DashboardStats>("/dashboard/stats");
    return data;
  },
};
