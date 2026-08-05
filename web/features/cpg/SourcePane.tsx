"use client";

import { FolderOpen, Play } from "lucide-react";
import { useRef } from "react";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PanelShell } from "@/components/workbench/PanelShell";
import { SAMPLES } from "@/lib/samples";
import { useCpgSource } from "./provider";

/**
 * Where a CPG comes from: a bundled sample, a file, or whatever is in the
 * editor. Shared by F2-A and extraction, which both start the same way.
 */
export default function SourcePane() {
  const cpg = useCpgSource();
  const input = useRef<HTMLInputElement>(null);

  return (
    <PanelShell
      title="소스"
      actions={
        <>
          <Button variant="ghost" size="icon-xs" aria-label="파일 열기" onClick={() => input.current?.click()}>
            <FolderOpen />
          </Button>
          <input
            ref={input}
            type="file"
            hidden
            accept=".c,.h,.cpp,.cc,.cxx,.hpp,.hxx,.java,.json"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) cpg.open(file);
              event.target.value = "";
            }}
          />
          <Button size="xs" onClick={cpg.analyse} disabled={cpg.analyzing}>
            <Play />
            {cpg.analyzing ? "분석 중…" : "분석"}
          </Button>
        </>
      }
    >
      <div className="space-y-3 p-2.5">
        <div className="space-y-1">
          <label className="text-2xs text-ink-muted" htmlFor="cpg-sample">
            예제
          </label>
          <Select value={cpg.sampleId} onValueChange={cpg.pick}>
            <SelectTrigger id="cpg-sample" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SAMPLES.map((sample) => (
                <SelectItem key={sample.id} value={sample.id}>
                  {sample.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-2xs leading-relaxed text-ink-faint">{cpg.sample.description}</p>
        </div>

        <dl className="space-y-1 border-t border-line pt-2 text-2xs">
          <div className="flex justify-between gap-2">
            <dt className="text-ink-faint">파일</dt>
            <dd className="truncate font-mono text-ink-muted">{cpg.name}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-ink-faint">언어</dt>
            <dd className="font-mono text-ink-muted">{cpg.language}</dd>
          </div>
          {cpg.response && (
            <>
              <div className="flex justify-between gap-2">
                <dt className="text-ink-faint">메서드</dt>
                <dd className="font-mono text-ink-muted">{cpg.response.method_count}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-ink-faint">핸들러</dt>
                <dd className="font-mono text-ink-muted">{cpg.response.f2a.handler_maps?.length ?? 0}</dd>
              </div>
            </>
          )}
        </dl>

        <p className="border-t border-line pt-2 text-2xs leading-relaxed text-ink-faint">
          소스 또는 CPG JSON 을 열 수 있습니다. 편집기에서 바로 수정한 뒤 ‘분석’을 누르세요.
        </p>
      </div>
    </PanelShell>
  );
}
