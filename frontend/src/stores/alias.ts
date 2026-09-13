import { defineStore } from "pinia";
import { aliasApi } from "@/api";
import type { Alias, AliasBatchResult, AliasDeleteResult } from "@/api/types";

interface AliasState {
  aliases: Alias[];
  domains: string[];
  loading: boolean;
  lastCreatedId: number | null;
}

export const useAliasStore = defineStore("alias", {
  state: (): AliasState => ({
    aliases: [],
    domains: [],
    loading: false,
    lastCreatedId: null,
  }),

  actions: {
    async fetchByAccount(accountId: number): Promise<void> {
      this.loading = true;
      try {
        this.aliases = await aliasApi.listByAccount(accountId);
      } finally {
        this.loading = false;
      }
    },

    async fetchDomains(accountId: number, refresh = false): Promise<void> {
      const result = await aliasApi.domains(accountId, refresh);
      this.domains = result.domains;
    },

    async batchGenerate(options: {
      count: number;
      domain: string;
      accountId?: number | null;
      prefix?: string;
      length?: number;
    }): Promise<AliasBatchResult> {
      return aliasApi.batchGenerate(options);
    },

    async create(accountId: number, address: string): Promise<Alias> {
      const alias = await aliasApi.create(accountId, address);
      this.aliases.push(alias);
      this.lastCreatedId = alias.id;
      return alias;
    },

    async createAuto(address: string, accountId?: number | null, silent = false): Promise<Alias> {
      const alias = await aliasApi.createAuto(address, accountId, silent);
      if (!this.aliases.some((item) => item.id === alias.id)) {
        this.aliases.push(alias);
      }
      this.lastCreatedId = alias.id;
      return alias;
    },

    async remove(id: number): Promise<void> {
      await aliasApi.remove(id);
      this.aliases = this.aliases.filter((alias) => alias.id !== id);
    },

    async removeMany(ids: number[]): Promise<AliasDeleteResult> {
      const result = await aliasApi.removeMany(ids);
      const deleted = new Set(result.items.filter((item) => item.ok).map((item) => item.alias_id));
      this.aliases = this.aliases.filter((alias) => !deleted.has(alias.id));
      return result;
    },

    async setDefaultSender(id: number, sender: "email" | "name-email"): Promise<void> {
      const updated = await aliasApi.setDefaultSender(id, sender);
      const index = this.aliases.findIndex((alias) => alias.id === id);
      if (index >= 0) this.aliases[index] = updated;
    },

    async setDisplayName(id: number, displayName: string): Promise<void> {
      const updated = await aliasApi.setDisplayName(id, displayName);
      const index = this.aliases.findIndex((alias) => alias.id === id);
      if (index >= 0) this.aliases[index] = updated;
    },
  },
});
