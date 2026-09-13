import { defineStore } from "pinia";
import { accountApi } from "@/api";
import type { Account } from "@/api/types";

interface AccountState {
  accounts: Account[];
  loading: boolean;
  currentAccountId: number | null;
}

export const useAccountStore = defineStore("account", {
  state: (): AccountState => ({
    accounts: [],
    loading: false,
    currentAccountId: null,
  }),

  getters: {
    currentAccount: (state): Account | null =>
      state.accounts.find((account) => account.id === state.currentAccountId) ?? null,
  },

  actions: {
    async fetchAll(): Promise<void> {
      this.loading = true;
      try {
        this.accounts = await accountApi.list();
        if (this.currentAccountId === null && this.accounts.length > 0) {
          this.currentAccountId = this.accounts[0]!.id;
        }
      } finally {
        this.loading = false;
      }
    },

    async create(email: string, password: string, silent = false): Promise<Account> {
      const account = await accountApi.create(email, password, silent);
      this.accounts.push(account);
      return account;
    },

    async remove(id: number): Promise<void> {
      await accountApi.remove(id);
      this.accounts = this.accounts.filter((account) => account.id !== id);
      if (this.currentAccountId === id) {
        this.currentAccountId = this.accounts[0]?.id ?? null;
      }
    },

    async verify(id: number): Promise<void> {
      const result = await accountApi.verify(id);
      const account = this.accounts.find((item) => item.id === id);
      if (account) {
        account.session_state = result.session_state;
      }
    },

    select(id: number): void {
      this.currentAccountId = id;
    },
  },
});
