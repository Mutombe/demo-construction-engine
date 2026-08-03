import axios, { type AxiosError, type AxiosRequestConfig } from "axios";
import { useAuthStore } from "@/features/auth/store";

export const api = axios.create({ baseURL: "" });

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Single-flight refresh: many parallel 401s share one refresh call.
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = axios
      .post("/api/v1/auth/refresh", null, { withCredentials: true })
      .then((res) => {
        const { access_token, user } = res.data;
        useAuthStore.getState().setSession(access_token, user);
        return access_token as string;
      })
      .catch(() => {
        useAuthStore.getState().clearSession();
        return null;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as (AxiosRequestConfig & { _retried?: boolean }) | undefined;
    const url = original?.url ?? "";
    if (
      error.response?.status === 401 &&
      original &&
      !original._retried &&
      !url.includes("/auth/login") &&
      !url.includes("/auth/refresh")
    ) {
      const token = await refreshAccessToken();
      if (token) {
        original._retried = true;
        original.headers = { ...original.headers, Authorization: `Bearer ${token}` };
        return api.request(original);
      }
    }
    return Promise.reject(error);
  },
);

/** Orval mutator: every generated hook calls through this instance. */
export function apiMutator<T>(config: AxiosRequestConfig): Promise<T> {
  return api.request<T>(config).then((res) => res.data);
}

export { refreshAccessToken };
