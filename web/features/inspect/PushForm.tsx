"use client";

import { ExternalLink, Loader2, Upload } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Origin, PushResult } from "@/lib/api/types";
import { usePushBranch } from "@/lib/inspect/queries";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * Put the fix on a branch of the repository it came from.
 *
 * Only reachable for a run that was cloned, because only then is there a remote
 * and a base commit. The server clones that commit again and applies the patch
 * there, so a remote that has moved since the scan produces a refusal rather
 * than a force-push -- see `agent/vcs.push`.
 *
 * The token is the awkward part and the copy does not pretend otherwise. This
 * service has no login, so there is no account to hang a stored credential on;
 * a per-request token that is never written down is the version of this that
 * cannot outlive the request. Saying so is part of asking for it.
 */
export default function PushForm({
  origin,
  findingIds,
  onDone,
}: {
  origin: Origin;
  findingIds: string[];
  onDone: () => void;
}) {
  const [runId] = useRunId();
  const push = usePushBranch(runId);
  const [branch, setBranch] = useState(`ssat/fix-${origin.commit?.slice(0, 7) ?? "1"}`);
  const [token, setToken] = useState("");
  const [pr, setPr] = useState(true);
  const [result, setResult] = useState<PushResult | null>(null);

  const github = (origin.url ?? "").includes("github.com");

  if (result) {
    return (
      <div className="space-y-2 rounded-md border border-ok/40 bg-ok-wash px-3 py-3">
        <p className="text-xs text-ink">
          <strong className="font-semibold">{result.branch}</strong> 브랜치를 올렸습니다.
          {result.applied.length > 0 && ` ${result.applied.length}건이 들어갔습니다.`}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {result.pr_url && (
            <Button size="sm" variant="outline" asChild>
              <a href={result.pr_url} target="_blank" rel="noreferrer">
                <ExternalLink className="size-3.5" />
                풀 리퀘스트 열기
              </a>
            </Button>
          )}
          {result.compare_url && !result.pr_url && (
            <Button size="sm" variant="outline" asChild>
              <a href={result.compare_url} target="_blank" rel="noreferrer">
                <ExternalLink className="size-3.5" />
                비교 화면에서 열기
              </a>
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={onDone}>
            끝
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form
      className="space-y-3 rounded-md border border-line px-3 py-3"
      onSubmit={(event) => {
        event.preventDefault();
        void push
          .mutateAsync({ findingIds, branch: branch.trim(), token: token.trim(), openPullRequest: pr && github })
          .then((next) => {
            // Cleared the moment it has been used. It was only ever in this
            // component's state and this request's body.
            setToken("");
            setResult(next);
          });
      }}
    >
      <p className="text-xs font-medium text-ink-strong">브랜치로 올리기</p>
      <p className="font-mono text-2xs text-ink-faint">
        {origin.label} · {origin.commit?.slice(0, 7)} 위에 올립니다
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="push-branch">브랜치 이름</Label>
          <Input id="push-branch" value={branch} onChange={(event) => setBranch(event.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="push-token">토큰</Label>
          <Input
            id="push-token"
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="쓰기 권한이 있는 토큰"
            autoComplete="off"
          />
        </div>
      </div>

      {github && (
        <Label className="flex items-center gap-2 text-xs font-normal">
          <Checkbox checked={pr} onCheckedChange={(next) => setPr(next === true)} />
          풀 리퀘스트도 함께 열기
        </Label>
      )}

      <p className="text-2xs leading-relaxed text-ink-faint">
        토큰은 이 요청에만 씁니다. 저장하지 않고, 기록에도 남기지 않으며, 이 검사에 적힌 저장소 주소에만 사용합니다.
        {!github && " 풀 리퀘스트는 GitHub 에서만 자동으로 열 수 있습니다 — 다른 곳은 브랜치만 올리고 링크를 드립니다."}
      </p>

      <Button type="submit" size="sm" disabled={!branch.trim() || !token.trim() || push.isPending}>
        {push.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}
        올리기
      </Button>
    </form>
  );
}
