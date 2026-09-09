"use client";

import { Columns2, Loader2, Sparkles } from "lucide-react";
import { useState } from "react";

import DiffView from "@/components/editor/DiffView.lazy";
import { Patch } from "@/components/panel/patch";
import { Button } from "@/components/ui/button";
import { splice } from "@/lib/inspect/splice";
import { isFixable } from "@/lib/inspect/filter";
import { wireId, type UiFinding } from "@/lib/model/finding";
import { useFile, useProposeFix } from "@/lib/run/queries";
import { useRunId } from "@/lib/run/use-run-id";

export default function FixPatch({ finding }: { finding: UiFinding }) {
  const [runId] = useRunId();
  const propose = useProposeFix(runId);
  const [wide, setWide] = useState(false);

  if (!isFixable(finding)) {
    return (
      <div className="space-y-2 rounded-md border border-line bg-field px-3 py-2.5">
        <p className="text-xs text-ink-muted">
          이 문제를 그 줄만 바꿔서 고치는 코드는 아직 없습니다.
        </p>
        <Button size="sm" variant="outline" disabled={propose.isPending} onClick={() => propose.mutate(wireId(finding.id))}>
          {propose.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
          고칠 코드 만들기
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {finding.diff ? <Patch diff={finding.diff} /> : <PlainReplacement finding={finding} />}
      <Button size="sm" variant="ghost" onClick={() => setWide(!wide)}>
        <Columns2 className="size-3.5" />
        {wide ? "나란히 보기 닫기" : "나란히 보기"}
      </Button>
      {wide && <SideBySide finding={finding} />}
    </div>
  );
}

function PlainReplacement({ finding }: { finding: UiFinding }) {
  return (
    <pre className="overflow-x-auto rounded-md border border-line bg-field p-2 font-mono text-2xs leading-relaxed text-ok">
      {finding.replacement}
    </pre>
  );
}

function SideBySide({ finding }: { finding: UiFinding }) {
  const [runId] = useRunId();
  const file = useFile(runId, finding.primary.file);

  if (file.isPending) return <p className="p-2 text-2xs text-ink-faint">파일을 읽는 중…</p>;
  if (!file.data) return <p className="p-2 text-2xs text-ink-faint">이 파일을 읽을 수 없습니다.</p>;

  return (
    <div className="h-72 overflow-hidden rounded-md border border-line">
      <DiffView
        original={file.data.content}
        modified={splice(file.data.content, finding)}
        language={file.data.language}
      />
    </div>
  );
}
