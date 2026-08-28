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

/**
 * The fix, as the change it would make.
 *
 * Two renderings of one diff and they are not redundant. The unified patch is
 * four lines in a column and answers "what changes" at a glance; the side-by-side
 * is for a fix long enough that a `-` and its `+` land rows apart, which is where
 * a `<pre>` stops being readable. The second is behind a button because it loads
 * Monaco.
 *
 * A finding with advice and no code gets a button instead. That is not a gap to
 * apologise for: the specialist proposes a fix only when it fits the lines the
 * anchor resolved to, and often it does not -- so the honest offer is to go and
 * ask for one.
 */
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

/**
 * The replacement on its own, when the server computed no diff.
 *
 * Reachable for a fix that arrived from `/propose` in a report the run then
 * re-saved -- the diff is built from the file as it was read, and a finding
 * whose file could not be re-read has the code but not the comparison.
 */
function PlainReplacement({ finding }: { finding: UiFinding }) {
  return (
    <pre className="overflow-x-auto rounded-md border border-line bg-field p-2 font-mono text-2xs leading-relaxed text-ok">
      {finding.replacement}
    </pre>
  );
}

/**
 * The file before and after, side by side.
 *
 * Splices in the browser purely to *show* it. Nothing is written from here and
 * nothing downloadable is built from it -- the patch that leaves is the one the
 * server splices, so a disagreement between this and that would be a display
 * bug rather than a corrupted file. Which is why `lib/inspect/splice` is allowed
 * to be the simpler, unchecked version.
 */
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
