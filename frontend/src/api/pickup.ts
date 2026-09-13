import client from "./client";
import type { Message, PickupBatchItem, PickupResolve, PickupResponse } from "./types";

export interface PickupOptions {
  amount?: number;
  markRead?: boolean;
  unreadOnly?: boolean;
  refresh?: boolean;
}

export const pickupApi = {
  async fetch(accountKey: string, address: string, options: PickupOptions = {}): Promise<PickupResponse> {
    const { data } = await client.get<PickupResponse>(
      `/pickup/${encodeURIComponent(accountKey)}/${encodeURIComponent(address)}`,
      {
        params: {
          amount: options.amount ?? 25,
          mark_read: options.markRead ?? false,
          unread_only: options.unreadOnly ?? false,
          refresh: options.refresh ?? false,
        },
      },
    );
    return data;
  },

  async fetchBody(
    accountKey: string,
    address: string,
    messageId: string,
    format: "html" | "text" = "html",
  ): Promise<string> {
    const { data } = await client.get<{ body: string }>(
      `/pickup/${encodeURIComponent(accountKey)}/${encodeURIComponent(address)}/messages/${encodeURIComponent(messageId)}/body`,
      { params: { format } },
    );
    return data.body;
  },

  async batch(pickupUrls: string[], amount = 25): Promise<PickupBatchItem[]> {
    const { data } = await client.post<{ results: PickupBatchItem[] }>("/pickup/batch", {
      pickup_urls: pickupUrls,
      amount,
    });
    return data.results;
  },

  async resolve(pickupUrl: string): Promise<PickupResolve> {
    const { data } = await client.post<PickupResolve>("/pickup/resolve", { pickup_url: pickupUrl });
    return data;
  },
};

export type { Message };
