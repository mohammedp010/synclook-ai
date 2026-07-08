import axios from "axios";
import { Platform } from "react-native";

const DEFAULT_PROD_BASE_URL = "https://api.synclook.ai";

function getEnvBaseUrl(): string | null {
  const env = (
    globalThis as { process?: { env?: Record<string, string | undefined> } }
  ).process?.env;
  const raw = env?.EXPO_PUBLIC_API_BASE_URL?.trim();
  if (!raw) {
    return null;
  }
  return raw.replace(/\/+$/, "");
}

function getDefaultDevBaseUrl(): string {
  if (Platform.OS === "web") {
    const host = (
      globalThis as { location?: { hostname?: string } }
    ).location?.hostname;
    if (host && host !== "localhost" && host !== "127.0.0.1") {
      return `http://${host}:8000`;
    }
    return "http://localhost:8000";
  }

  // Android emulators can't reach host-loopback at localhost.
  if (Platform.OS === "android") {
    return "http://10.0.2.2:8000";
  }

  return "http://localhost:8000";
}

const envBaseUrl = getEnvBaseUrl();

export const BASE_URL = __DEV__
  ? (envBaseUrl ?? getDefaultDevBaseUrl())
  : (envBaseUrl ?? DEFAULT_PROD_BASE_URL);

export const api = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  timeout: 120_000,
  headers: {
    Accept: "application/json",
  },
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      "An unexpected error occurred";
    return Promise.reject(new Error(message));
  }
);
