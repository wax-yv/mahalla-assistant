"use client";

import { api, onUnauthorized, setCsrf } from "@/lib/api";

export type Me = {
  user: { id: string; username: string; display_name: string; role: string };
  csrf_token: string;
  demo_mode: boolean;
  version: string;
};

let me: Me | null = null;
const listeners = new Set<(value: Me | null) => void>();

export function subscribeMe(listener: (value: Me | null) => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function emit(value: Me | null) {
  me = value;
  listeners.forEach((listener) => listener(value));
}

export function getMe() {
  return me;
}

export async function refreshMe(): Promise<Me | null> {
  try {
    const data = await api.get<Me>("/auth/me");
    setCsrf(data.csrf_token);
    emit(data);
    return data;
  } catch {
    emit(null);
    return null;
  }
}

export async function login(username: string, password: string): Promise<Me> {
  const data = await api.post<Me>("/auth/login", { username, password });
  setCsrf(data.csrf_token);
  emit(data);
  return data;
}

export async function logout() {
  try {
    await api.post("/auth/logout");
  } finally {
    emit(null);
  }
}

export function initAuthRedirect(onRedirect: () => void) {
  onUnauthorized(onRedirect);
}
