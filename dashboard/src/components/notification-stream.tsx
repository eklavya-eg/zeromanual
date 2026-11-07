"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bell, X } from "lucide-react";
import Link from "next/link";
import { createContext, useContext, useEffect, useState } from "react";

import { notificationSocketUrl } from "@/lib/api";
import type { AppNotification, NotificationSocketMessage } from "@/lib/types";

function notificationKey(notification: AppNotification) {
  return notification.kind === "workflow_run"
    ? `workflow:${notification.run_id}:${notification.attempt_count}`
    : `agent:${notification.job_id}`;
}

const NotificationStreamContext = createContext(false);

export function useNotificationStream() {
  return useContext(NotificationStreamContext);
}

export function NotificationStream({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [latest, setLatest] = useState<AppNotification | null>(null);

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
        queryClient.invalidateQueries({ queryKey: ["notifications"] });
        queryClient.invalidateQueries({ queryKey: ["runs"] });
      };
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as NotificationSocketMessage;
        if (message.type !== "notification") return;
        queryClient.setQueryData<AppNotification[]>(
          ["notifications"],
          (current = []) => [
            message.data,
            ...current.filter((item) => notificationKey(item) !== notificationKey(message.data)),
          ],
        );
        if (message.data.kind === "workflow_run") {
          queryClient.invalidateQueries({ queryKey: ["runs"] });
          queryClient.invalidateQueries({ queryKey: ["run-steps", message.data.run_id] });
        }
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
              <p className="text-sm font-bold">{latest.kind === "workflow_run" ? latest.workflow_name : latest.agent_name} {latest.status}</p>
              <p className="mt-1 break-all text-xs text-[var(--muted)]">{latest.kind === "workflow_run" ? `Run ${latest.run_id}` : `Task ${latest.job_id}`}</p>
              <Link href={latest.kind === "workflow_run" ? `/runs/${latest.run_id}` : "/notifications"} onClick={() => setLatest(null)} className="mt-2 inline-block text-xs font-semibold text-[var(--blue)]">{latest.kind === "workflow_run" ? "View run output" : "View response"}</Link>
            </div>
            <button onClick={() => setLatest(null)} aria-label="Dismiss notification" className="grid size-8 place-items-center rounded-xl bg-black/[0.04]"><X className="size-3.5" /></button>
          </div>
        </div>
      )}
    </NotificationStreamContext.Provider>
  );
}
