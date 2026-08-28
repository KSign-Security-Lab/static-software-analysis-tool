"use client";

import { RefreshCw, ServerCrash } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useBackend } from "@/lib/inspect/backend";

/**
 * The backend is not answering, said once and where it matters.
 *
 * Everything on this surface is the server's: the run list, the report, the
 * patch. When it cannot be reached, every one of those renders as an absence --
 * no scans, no findings, nothing to patch -- and an absence is indistinguishable
 * from an answer. So this is a strip rather than a toast: a toast is gone in four
 * seconds and the misleading empty screen stays.
 *
 * Names the URL it tried, because the failure is almost always that the address
 * is right for the machine serving the page and wrong for the one reading it --
 * the API host is derived from `window.location.hostname`, so a page opened over
 * a LAN or tailnet address expects the API on that same host.
 */
export default function BackendDown() {
  const { down, message, base, retry } = useBackend();
  if (!down) return null;

  return (
    <div
      role="alert"
      className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-danger/40 bg-danger-wash px-3 py-2"
    >
      <ServerCrash className="size-4 shrink-0 text-danger" aria-hidden />
      <span className="min-w-0 flex-1 text-xs text-ink">
        {message || `백엔드(${base})에 연결할 수 없습니다.`}
      </span>
      <Button size="sm" variant="outline" onClick={retry}>
        <RefreshCw className="size-3.5" />
        다시 시도
      </Button>
      <p className="w-full text-2xs leading-relaxed text-ink-faint">
        API 주소는 이 페이지의 호스트에서 그대로 가져옵니다 — 즉 <code className="font-mono">{base}</code> 가 열려
        있어야 합니다. 다른 곳에 있다면 <code className="font-mono">NEXT_PUBLIC_API_URL</code> 로 지정하십시오.
      </p>
    </div>
  );
}
