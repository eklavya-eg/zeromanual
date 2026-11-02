"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bell, X } from "lucide-react";
import Link from "next/link";
import { createContext, useContext, useEffect, useState } from "react";

import { notificationSocketUrl } from "@/lib/api";
import type { NotificationSocketMessage, SubAgentNotification } from "@/lib/types";

const NotificationStreamContext = createContext(false);

export function useNotificationStream() {
  return useContext(NotificationStreamContext);
}

export function NotificationStream({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [latest, setLatest] = useState<SubAgentNotification | null>(null);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let toastTimer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;
    let retryDelay = 1_000;

    function connect() {
      socket = new WebSocket(notificationSocketUrl());
      socket.onopen = () => {
        retryDelay = 1_000;
        setConnected(true);
      };
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as NotificationSocketMessage;
        if (message.type !== "notification") return;
        queryClient.setQueryData<SubAgentNotification[]>(
          ["notifications"],
          (current = []) => [
            message.data,
            ...current.filter((item) => item.job_id !== message.data.job_id),
          ],
        );
        setLatest(message.data);
        if (toastTimer) clearTimeout(toastTimer);
        toastTimer = setTimeout(() => setLatest(null), 8_000);
      };
      socket.onclose = () => {
        setConnected(false);
        if (stopped) return;
        reconnectTimer = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 15_000);
      };
    }

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (toastTimer) clearTimeout(toastTimer);
      socket?.close();
    };
  }, [queryClient]);

  return (
    <NotificationStreamContext.Provider value={connected}>
      {children}
      {latest && (
        <div className="fixed bottom-5 right-5 z-[90] w-[min(400px,calc(100vw-2.5rem))] rounded-[22px] border border-black/[0.08] bg-white p-4 shadow-2xl">
          <div className="flex items-start gap-3">
            <div className="grid size-10 shrink-0 place-items-center rounded-2xl bg-blue-50 text-[var(--blue)]"><Bell className="size-4" /></div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold">{latest.agent_name} {latest.status}</p>
              <p className="mt-1 text-xs text-[var(--muted)]">Task {latest.job_id}</p>
              <Link href="/notifications" onClick={() => setLatest(null)} className="mt-2 inline-block text-xs font-semibold text-[var(--blue)]">View response</Link>
            </div>
            <button onClick={() => setLatest(null)} aria-label="Dismiss notification" className="grid size-8 place-items-center rounded-xl bg-black/[0.04]"><X className="size-3.5" /></button>
          </div>
        </div>
      )}
    </NotificationStreamContext.Provider>
  );
}
