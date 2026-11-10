import { create } from "zustand";
import { SAMPLE_CHATS } from "@/data/sample";
import { api, isLive } from "@/services/api";

export interface ChatRow {
  id: string;
  title: string;
}

interface ChatsState {
  chats: ChatRow[];
  query: string;
  load: (query?: string) => Promise<void>;
}

/** The sidebar's "Recent" list. Live: from the server (title search also looks inside messages). */
export const useChatsStore = create<ChatsState>((set, get) => ({
  chats: isLive ? [] : SAMPLE_CHATS,
  query: "",
  load: async (query) => {
    const q = query ?? get().query;
    set({ query: q });
    if (!isLive) return;
    try {
      const rows = await api.chats(q);
      set({ chats: rows.map((r) => ({ id: r.id, title: r.title })) });
    } catch {
      /* keep the last list; the bootstrap error banner explains an unreachable server */
    }
  },
}));
