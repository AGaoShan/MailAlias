import { defineStore } from "pinia";
import { aliasApi } from "@/api";
import type { Alias } from "@/api/types";

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

    async fetchDomains(accountId: number): Promise<void> {
      const result = await aliasApi.domains(accountId);
      this.domains = result.domains;
    },

    async create(accountId: number, address: string): Promise<Alias> {
      const alias = await aliasApi.create(accountId, address);
      this.aliases.push(alias);
      this.lastCreatedId = alias.id;
      return alias;
    },

    async remove(id: number): Promise<void> {
      await aliasApi.remove(id);
      this.aliases = this.aliases.filter((alias) => alias.id !== id);
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
