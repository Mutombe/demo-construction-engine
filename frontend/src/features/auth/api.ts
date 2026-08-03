import axios from "axios";
import { api, refreshAccessToken } from "@/lib/api/axios";
import { useAuthStore, type SessionUser } from "./store";

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: SessionUser;
}

export async function login(email: string, password: string): Promise<SessionUser> {
  const res = await axios.post<TokenResponse>(
    "/api/v1/auth/login",
    { email, password },
    { withCredentials: true },
  );
  useAuthStore.getState().setSession(res.data.access_token, res.data.user);
  return res.data.user;
}

export async function logout(): Promise<void> {
  try {
    await api.post("/api/v1/auth/logout", null, { withCredentials: true });
  } finally {
    useAuthStore.getState().clearSession();
  }
}

/** Boot-time silent session restore from the refresh cookie. */
export async function restoreSession(): Promise<void> {
  try {
    await refreshAccessToken();
  } finally {
    useAuthStore.getState().setInitialized();
  }
}
