import { useChatStore } from "@/store/chatStore";
import { useChatsStore } from "@/store/chatsStore";
import { useModelsStore } from "@/store/modelsStore";
import { useSettingsStore } from "@/store/settingsStore";
import { api, isLive } from "./api";

/**
 * First load. Mock mode needs nothing. Live mode asks the server for the model registry, settings,
 * month spend and recent chats, and repairs any saved preference that names a model that no longer exists.
 * Throws an ApiError (with a readable message) when the backend cannot be reached.
 */
export async function bootstrap(): Promise<void> {
  if (!isLive) return;
  const [cfg, models] = await Promise.all([api.config(), api.models()]);
  useModelsStore.getState().setFromConfig(cfg, models);
  useSettingsStore.getState().hydrateFromServer(cfg.settings, cfg.monthUsd, cfg.readingUsd);
  const chat = useChatStore.getState();
  chat.applyServerDefaults(cfg, models.map((m) => m.id));
  await Promise.all([useChatsStore.getState().load(), chat.refreshContext(), useSettingsStore.getState().loadMemory()]);
}
