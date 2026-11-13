/** Accounts: sign up, sign in, password, account deletion and the operator's admin calls. */
import { API_URL, ApiError, apiFetch, toError } from "./api";

export interface Account {
  id: number;
  email: string;
  isAdmin: boolean;
  monthCapUsd: number;
  monthSpentUsd: number;
}

export interface AuthConfig {
  authRequired: boolean;
  signupOpen: boolean;
  inviteRequired: boolean;
  passwordResetByEmail: boolean;
  minPasswordLength: number;
  siteName: string;
  contactEmail: string;
}

export interface AdminUser {
  id: number;
  email: string;
  created: number;
  lastLogin: number | null;
  isAdmin: boolean;
  disabled: boolean;
  monthlyCap: number | null;
  effectiveCap: number;
  monthSpentUsd: number;
  chats: number;
}

export interface AdminStats {
  users: number;
  chats: number;
  monthSpentUsd: number;
  globalCapUsd: number;
  activeRuns: number;
  maxConcurrentRuns: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await apiFetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection and try again.", 0);
  }
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}

const post = (body?: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const auth = {
  config: () => request<AuthConfig>("/api/auth/config"),
  /** The signed-in account, or null when nobody is signed in. */
  me: async (): Promise<Account | null> => {
    try {
      return await request<Account>("/api/auth/me");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return null;
      throw e;
    }
  },
  login: (email: string, password: string) => request<Account>("/api/auth/login", post({ email, password })),
  signup: (email: string, password: string, inviteCode?: string) => request<Account>("/api/auth/signup", post({ email, password, inviteCode: inviteCode || undefined })),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", post()),
  forgot: (email: string) => request<{ message: string }>("/api/auth/forgot", post({ email })),
  reset: (token: string, password: string) => request<{ ok: boolean }>("/api/auth/reset", post({ token, password })),
  changePassword: (current: string, next: string) => request<{ ok: boolean }>("/api/auth/password", post({ current, new: next })),
  deleteAccount: (password: string) => request<{ deleted: boolean }>("/api/auth/account", post({ password }, "DELETE")),
  adminUsers: () => request<AdminUser[]>("/api/admin/users"),
  adminStats: () => request<AdminStats>("/api/admin/stats"),
  adminPatch: (id: number, patch: { disabled?: boolean; isAdmin?: boolean; monthlyCap?: number; resetCap?: boolean }) =>
    request<{ ok: boolean }>(`/api/admin/users/${id}`, post(patch, "PATCH")),
};
