"use client";

import { SAMPLE_CHATS } from "@/data/sample";
import { api, isLive } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { useChatsStore } from "@/store/chatsStore";
import { useSettingsStore } from "@/store/settingsStore";
import { toast, useUiStore } from "@/store/uiStore";
import { Modal, ModalBody } from "../ui/Modal";

/**
 * C42: deleting a chat removes it from every store, index and cache, and asks about the memories
 * it created. In both ChatGPT and Claude, deleting a chat does NOT delete its memories; here the
 * user decides, every time.
 */
export default function DeleteChatDialog() {
  const id = useUiStore((s) => s.deleteChatId);
  const close = useUiStore((s) => s.close);
  const title = useChatsStore((s) => s.chats.find((c) => c.id === id)?.title ?? SAMPLE_CHATS.find((c) => c.id === id)?.title ?? "this chat");

  const remove = async (deleteMemories: boolean) => {
    try {
      const r = isLive ? await api.deleteChat(id, deleteMemories) : { factsDeleted: 0 };
      close();
      if (useChatStore.getState().chatId === id) useChatStore.getState().newChat();
      await useChatsStore.getState().load();
      if (deleteMemories) await useSettingsStore.getState().loadMemory();
      toast(deleteMemories ? `Chat deleted, and ${r.factsDeleted} remembered facts` : "Chat deleted; its memories were kept");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not delete the chat");
    }
  };

  return (
    <Modal title="Delete this chat?" onClose={close} maxWidth={520} footer={<button type="button" className="btn" onClick={close}>Cancel</button>}>
      <ModalBody>
        <span>"{title}" will be removed from every store and search index. What about the facts it taught me?</span>
        <button type="button" className="mrow" onClick={() => void remove(false)}>
          <span className="mrow-main"><span className="strong">Delete the chat, keep its memories</span><span className="hint">Facts like your preferences stay available in other chats</span></span>
        </button>
        <button type="button" className="mrow" onClick={() => void remove(true)}>
          <span className="mrow-main"><span className="strong">Delete the chat and its memories</span><span className="hint">Remembered facts from this chat are removed everywhere</span></span>
        </button>
      </ModalBody>
    </Modal>
  );
}
