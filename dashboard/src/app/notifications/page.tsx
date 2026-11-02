"use client";

import { useQuery } from "@tanstack/react-query";
import { Bell, Bot, Clock3, Wifi, WifiOff } from "lucide-react";

import { useNotificationStream } from "@/components/notification-stream";
import { QueryAlert } from "@/components/query-alert";
import { Card, EmptyState, PageHeader, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export default function NotificationsPage() {
  const connected = useNotificationStream();
  const notificationsQuery = useQuery({
    queryKey: ["notifications"],
    queryFn: api.notifications.list,
  });
  const notifications = notificationsQuery.data ?? [];

  return (
    <div>
      <PageHeader
        eyebrow="Live results"
        title="Notifications"
        description="Manual sub-agent results arrive here over WebSockets. Payloads and responses expire from Redis automatically."
        action={
          <div className={`flex items-center gap-2 rounded-full px-3 py-2 text-xs font-semibold ${connected ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
            {connected ? <Wifi className="size-4" /> : <WifiOff className="size-4" />}
            {connected ? "Live" : "Reconnecting"}
          </div>
        }
      />
      <QueryAlert show={notificationsQuery.isError} />

      {notifications.length ? (
        <div className="space-y-4">
          {notifications.map((notification) => (
            <Card key={notification.job_id} className="overflow-hidden p-0">
              <div className="flex flex-col gap-4 border-b border-black/[0.06] p-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                  <div className="grid size-11 place-items-center rounded-2xl bg-blue-50 text-[var(--blue)]"><Bot className="size-5" /></div>
                  <div>
                    <h2 className="font-semibold">{notification.agent_name}</h2>
                    <p className="mt-1 font-mono text-[10px] text-[var(--muted)]">{notification.job_id}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5 text-xs text-[var(--muted)]"><Clock3 className="size-3.5" />{formatDateTime(notification.completed_at)}</div>
                  <StatusBadge tone={notification.status === "completed" ? "success" : "danger"}>{notification.status}</StatusBadge>
                </div>
              </div>
              <div className="grid gap-4 p-5 lg:grid-cols-2">
                <section>
                  <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-[var(--muted)]">Request payload</p>
                  <pre className="max-h-72 overflow-auto rounded-2xl bg-[#171923] p-4 text-[11px] leading-5 text-[#dfe4ff]">{JSON.stringify(notification.payload, null, 2)}</pre>
                </section>
                <section>
                  <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-[var(--muted)]">Response</p>
                  {notification.error ? (
                    <div className="rounded-2xl bg-red-50 p-4 text-xs leading-5 text-red-700">{notification.error}</div>
                  ) : (
                    <pre className="max-h-72 overflow-auto rounded-2xl bg-[#f6f6f4] p-4 text-[11px] leading-5 text-[#3d4050]">{JSON.stringify(notification.response, null, 2)}</pre>
                  )}
                </section>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Card><EmptyState icon={<Bell className="size-5" />} title="No notifications yet" description="Invoke a sub-agent manually. Its result will appear here when the callback completes." /></Card>
      )}
    </div>
  );
}
