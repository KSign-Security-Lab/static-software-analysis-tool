"use client";

import { AlertTriangle, FileArchive, FileWarning, FolderGit2, FolderOpen, Loader2, Play, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import ModelMissing from "@/features/inspect/ModelMissing";
import type { IntakeSkip, RunSummary, UploadResult } from "@/lib/api/types";
import { filesFromDrop, isArchiveDrop } from "@/lib/run/drop";
import { useAgentHealth, useCloneRepo, useStartRun, useUpload, useUploadArchive } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";
import { cn } from "@/lib/utils";

/**
 * Give the tool some code, and press one button.
 *
 * Three ways in, because the three are genuinely different acts: a folder on
 * this machine, an archive somebody sent, and a repository that lives
 * elsewhere. Only the last of the three needs anything typed, and only the last
 * makes a push possible later -- which is why the origin is recorded rather than
 * inferred.
 *
 * Uploading and starting are deliberately two steps and not one. Indexing tells
 * you how much there is, and "1,204 files, 8,900 units" is the one moment to
 * find out you dropped `node_modules` -- before spending minutes and tokens on
 * it rather than after.
 */
export default function Intake({ run }: { run: RunSummary | undefined }) {
  const [runId, setRunId] = useRunId();
  const [uploaded, setUploaded] = useState<UploadResult | null>(null);
  const upload = useUpload();
  const archive = useUploadArchive();
  const clone = useCloneRepo();
  const health = useAgentHealth();
  const [over, setOver] = useState(0);

  // The run row is the truth once it exists; `uploaded` is only what this tab
  // just did, and it carries the one thing the row does not: how much was read.
  const indexed = uploaded?.run_id === runId ? uploaded : null;

  function accept(result: UploadResult) {
    setUploaded(result);
    setRunId(result.run_id);
  }

  /**
   * A drop anywhere on this screen, whatever tab is showing.
   *
   * It used to be the 폴더 tab's zone alone, so dropping a `.zip` -- onto a screen
   * whose middle tab is literally 압축 파일 -- did nothing at all, and dropping a
   * folder while that tab was open did nothing either. What was dropped is
   * knowable, so the tabs are for *picking* and the drop decides for itself.
   */
  async function drop(transfer: DataTransfer) {
    // A second drop while the first is still being read would create a second
    // run and leave the first orphaned -- and a big tree takes long enough that
    // dropping again is the natural thing to try.
    if (busy) return;
    const dropped = await filesFromDrop(transfer);
    if (dropped.length === 0) return;
    accept(
      isArchiveDrop(dropped)
        ? await archive.mutateAsync(dropped[0].file)
        : await upload.mutateAsync(dropped),
    );
  }

  // Includes the clone: it is the slowest of the three and the one most likely
  // to be pressed twice.
  const busy = upload.isPending || archive.isPending || clone.isPending;

  return (
    <div
      className="min-h-0 flex-1 overflow-auto"
      // Depth-counted: `dragleave` fires on every child the pointer crosses, so
      // a boolean flickers off over the very text describing the zone.
      onDragEnter={(event) => {
        event.preventDefault();
        setOver((n) => n + 1);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => setOver((n) => Math.max(0, n - 1))}
      onDrop={(event) => {
        event.preventDefault();
        setOver(0);
        void drop(event.dataTransfer);
      }}
    >
      {/* At the container, not inside a tab. The drop is handled for the whole
          screen, so the affordance has to be too -- dragging over the git tab
          worked and looked like nothing, which reads as a dead zone. */}
      <div
        className={cn(
          "mx-auto w-full max-w-2xl rounded-xl px-6 py-10 transition-colors",
          over > 0 && "bg-accent-wash/40 outline-2 outline-dashed outline-accent",
        )}
      >
        <h1 className="text-lg font-semibold text-ink-strong">검사할 코드</h1>
        <p className="mt-1 text-xs leading-relaxed text-ink-muted">
          폴더, 압축 파일, git 주소 가운데 하나를 주십시오. 폴더든 <code className="font-mono">.zip</code> 이든 이
          화면 아무 곳에나 끌어다 놓아도 됩니다. 읽고 나면 무엇을 얼마나 읽었는지 먼저 보여 드립니다.
        </p>

        {run?.status === "failed" && run.error && (
          <p className="mt-4 flex items-start gap-2 rounded-md border border-danger/40 bg-danger-wash px-3 py-2 text-xs text-ink">
            <AlertTriangle className="mt-px size-3.5 shrink-0 text-danger" aria-hidden />
            {run.error}
          </p>
        )}

        {over > 0 && (
          <p className="mt-4 flex items-center gap-2 text-xs font-medium text-accent-ink">
            <Upload className="size-4 shrink-0" aria-hidden />
            놓으면 바로 읽습니다 — 폴더든 .zip 이든 됩니다
          </p>
        )}

        {busy ? (
          <Reading kind={clone.isPending ? "clone" : "upload"} />
        ) : (
        <Tabs defaultValue="folder" className="mt-6">
          <TabsList>
            <TabsTrigger value="folder">
              <FolderOpen className="size-3.5" />
              폴더
            </TabsTrigger>
            <TabsTrigger value="zip">
              <FileArchive className="size-3.5" />
              압축 파일
            </TabsTrigger>
            <TabsTrigger value="git">
              <FolderGit2 className="size-3.5" />
              git 주소
            </TabsTrigger>
          </TabsList>

          <TabsContent value="folder">
            <FolderIntake onDone={accept} dragging={over > 0} busy={busy} />
          </TabsContent>
          <TabsContent value="zip">
            <ArchiveIntake onDone={accept} dragging={over > 0} busy={busy} />
          </TabsContent>
          <TabsContent value="git">
            <GitIntake onDone={accept} clone={clone} busy={busy} />
          </TabsContent>
        </Tabs>
        )}

        {/* Above the intake tabs, not beside the button: uploading still works
            without a model, and the reader should know before they choose a
            folder that the scan itself will not run. */}
        <ModelMissing health={health.data} />

        {runId && <Ready run={run} indexed={indexed} configured={health.data?.configured ?? true} />}
      </div>
    </div>
  );
}

/* -- the three ways in -------------------------------------------------------- */

function FolderIntake({
  onDone,
  dragging,
  busy,
}: {
  onDone: (result: UploadResult) => void;
  dragging: boolean;
  busy: boolean;
}) {
  const upload = useUpload();
  const picker = useRef<HTMLInputElement>(null);

  async function send(files: (File | { file: File; path: string })[]) {
    if (files.length === 0) return;
    onDone(await upload.mutateAsync(files));
  }

  return (
    <div
      className={cn(
        "mt-3 grid place-items-center gap-3 rounded-lg border border-dashed border-line-2 px-6 py-12 text-center transition-colors",
        dragging && "border-accent bg-accent-wash",
      )}
    >
      <Upload className={cn("size-6", dragging ? "text-accent-ink" : "text-ink-faint")} aria-hidden />
      <p className="text-sm text-ink-muted">폴더를 여기에 끌어다 놓으세요</p>
      <input
        ref={picker}
        type="file"
        multiple
        // Non-standard and the only way to pick a directory. React needs these
        // spelled as attributes; there is no typed prop for either.
        {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
        className="hidden"
        onChange={(event) => {
          void send(Array.from(event.target.files ?? []));
          event.target.value = "";
        }}
      />
      <Button variant="outline" size="sm" disabled={busy} onClick={() => picker.current?.click()}>
        {busy ? <Loader2 className="size-3.5 animate-spin" /> : <FolderOpen className="size-3.5" />}
        폴더 고르기
      </Button>
      <p className="text-2xs leading-relaxed text-ink-faint">
        소스 파일만 올라갑니다 — C · C++ · Java · Python · JS/TS · Go · Rust · C#.{" "}
        <code className="font-mono">.git</code>, <code className="font-mono">node_modules</code> 같은 디렉터리는 읽지도
        않고 건너뜁니다.
      </p>
    </div>
  );
}

function ArchiveIntake({
  onDone,
  dragging,
  busy,
}: {
  onDone: (result: UploadResult) => void;
  dragging: boolean;
  busy: boolean;
}) {
  const upload = useUploadArchive();
  const picker = useRef<HTMLInputElement>(null);

  return (
    <div
      className={cn(
        "mt-3 grid place-items-center gap-3 rounded-lg border border-dashed border-line-2 px-6 py-12 text-center transition-colors",
        dragging && "border-accent bg-accent-wash",
      )}
    >
      <FileArchive className={cn("size-6", dragging ? "text-accent-ink" : "text-ink-faint")} aria-hidden />
      <p className="text-sm text-ink-muted">.zip 파일을 끌어다 놓거나 고르세요</p>
      <input
        ref={picker}
        type="file"
        accept=".zip,application/zip"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void upload.mutateAsync(file).then(onDone);
          event.target.value = "";
        }}
      />
      <Button variant="outline" size="sm" disabled={busy} onClick={() => picker.current?.click()}>
        {busy ? <Loader2 className="size-3.5 animate-spin" /> : <FileArchive className="size-3.5" />}
        압축 파일 고르기
      </Button>
      <p className="text-2xs leading-relaxed text-ink-faint">
        소스 파일만 꺼냅니다 — C · C++ · Java · Python · JS/TS · Go · Rust · C#. 소스 20,000개, 합쳐서 500MB,
        한 파일 50MB까지.
      </p>
    </div>
  );
}

function GitIntake({
  onDone,
  clone,
  busy,
}: {
  onDone: (result: UploadResult) => void;
  clone: ReturnType<typeof useCloneRepo>;
  busy: boolean;
}) {
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");

  return (
    <form
      className="mt-3 space-y-3 rounded-lg border border-line px-4 py-4"
      onSubmit={(event) => {
        event.preventDefault();
        void clone.mutateAsync({ url: url.trim(), ref: ref.trim() || null }).then(onDone);
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="repo-url">저장소 주소</Label>
        <Input
          id="repo-url"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://github.com/owner/repo.git"
          inputMode="url"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="repo-ref">브랜치 또는 태그</Label>
        <Input
          id="repo-ref"
          value={ref}
          onChange={(event) => setRef(event.target.value)}
          placeholder="비워 두면 기본 브랜치"
        />
      </div>
      <Button type="submit" size="sm" disabled={!url.trim() || busy}>
        {busy ? <Loader2 className="size-3.5 animate-spin" /> : <FolderGit2 className="size-3.5" />}
        가져오기
      </Button>
      <p className="text-2xs leading-relaxed text-ink-faint">
        공개 저장소만, https 주소만 가져옵니다. 주소에 토큰을 넣지 마십시오 — 이 주소는 검사 기록에 그대로 남습니다.
        가져온 검사는 나중에 고친 것을 브랜치로 바로 올릴 수 있습니다.
      </p>
    </form>
  );
}

/**
 * Reading and parsing, which is not instant and used to look like nothing.
 *
 * The upload response comes back *after* the server has chunked and linked the
 * whole tree -- indexing is synchronous so the next screen has a file list to
 * render -- so on a real project this is seconds of a spinner inside a button
 * while the rest of the screen still invited another folder.
 */
function Reading({ kind }: { kind: "upload" | "clone" }) {
  return (
    <div className="mt-6 grid place-items-center gap-3 rounded-lg border border-line bg-surface px-6 py-12 text-center">
      <Loader2 className="size-6 animate-spin text-accent-ink" aria-hidden />
      <p className="text-sm text-ink">{kind === "clone" ? "저장소를 가져오는 중" : "코드를 읽는 중"}</p>
      <p className="max-w-sm text-2xs leading-relaxed text-ink-faint">
        파일을 읽고 함수 단위로 쪼개 서로의 호출 관계까지 이어 두는 중입니다. 큰 프로젝트는 몇 초 걸립니다 — 끝나면
        무엇을 얼마나 읽었는지 보여 드립니다.
      </p>
    </div>
  );
}

/* -- what arrived, and the one button ----------------------------------------- */

function Ready({
  run,
  indexed,
  configured,
}: {
  run: RunSummary | undefined;
  indexed: UploadResult | null;
  configured: boolean;
}) {
  const [runId] = useRunId();
  const { ensureAttached } = useRunStream();
  const start = useStartRun(runId, ensureAttached);
  const stats = indexed?.index ?? run?.index;
  const intake = indexed?.intake ?? run?.intake;
  const skipped = intake?.skipped ?? [];
  const reading = run?.status === "created" || run?.status === "indexing";

  return (
    <section className="mt-6 rounded-lg border border-line bg-surface px-4 py-4">
      {reading ? (
        <p className="flex items-center gap-2 text-sm text-ink-muted">
          <Loader2 className="size-4 animate-spin text-ink-faint" aria-hidden />
          코드를 읽는 중입니다
        </p>
      ) : (
        <>
          <dl className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs text-ink-muted">
            <Stat label="파일" value={stats?.files_indexed} />
            <Stat label="건너뜀" value={stats?.files_skipped} />
            <Stat label="단위" value={stats?.chunks} />
            <Stat label="연결" value={stats?.links} />
          </dl>
          {intake && intake.seen > intake.kept && (
            <p className="mt-2 text-2xs leading-relaxed text-ink-faint">
              파일 {intake.seen.toLocaleString()}개 가운데 {intake.kept.toLocaleString()}개를 읽습니다. 나머지는
              분석할 수 있는 언어가 아닙니다 — C · C++ · Java · Python · JS/TS · Go · Rust · C# 만 읽습니다.
            </p>
          )}
          {skipped.length > 0 && <Skipped skipped={skipped} />}
          {stats?.chunks === 0 ? (
            <p className="mt-3 text-xs text-warn">
              읽을 수 있는 코드가 없습니다. 다른 폴더나 브랜치를 주시거나, 지원하는 언어인지 확인해 주십시오.
            </p>
          ) : (
            <p className="mt-3 text-2xs leading-relaxed text-ink-faint">
              단위 하나하나를 읽으며 취약점을 찾습니다. 다 끝나기를 기다릴 필요는 없습니다 — 찾는 대로 쌓입니다.
            </p>
          )}
          <Button
            className="mt-3"
            // Not disabled for a missing model without saying why -- the strip
            // above says it, and a button that is grey for an unstated reason is
            // worse than one that explains itself.
            disabled={!runId || start.isPending || stats?.chunks === 0 || !configured}
            onClick={() => start.mutate({})}
          >
            {start.isPending ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
            검사 시작
          </Button>
        </>
      )}
    </section>
  );
}

/**
 * Files intake passed over, and what that costs.
 *
 * Said rather than done quietly, because it has a consequence the reader would
 * otherwise meet much later: a skipped file is not stored, so it will not be in
 * a patched-source download either. The alternative was refusing the whole
 * upload over one generated artifact, which cost them every other file.
 */
function Skipped({ skipped }: { skipped: IntakeSkip[] }) {
  // Grouped by reason, because the two are different facts about the tree and a
  // mixed list of ten paths says neither.
  const groups = (["too_large", "binary"] as const)
    .map((reason) => ({ reason, rows: skipped.filter((each) => each.reason === reason) }))
    .filter((group) => group.rows.length > 0);

  return (
    <div className="mt-3 space-y-2 rounded-md border border-warn/40 bg-warn-wash px-3 py-2">
      {groups.map(({ reason, rows }) => (
        <div key={reason} className="space-y-1">
          <p className="flex items-center gap-1.5 text-xs text-ink">
            <FileWarning className="size-3.5 shrink-0 text-warn" aria-hidden />
            {SKIP_TITLE[reason]} {rows.length}개를 건너뜁니다
          </p>
          <ul className="space-y-0.5">
            {rows.slice(0, 5).map((each) => (
              <li key={each.path} className="flex items-baseline gap-2 font-mono text-2xs text-ink-muted">
                <span className="min-w-0 truncate">{each.path}</span>
                <span className="shrink-0 text-ink-faint">{size(each.size)}</span>
              </li>
            ))}
            {rows.length > 5 && (
              <li className="font-mono text-2xs text-ink-faint">그 밖에 {rows.length - 5}개</li>
            )}
          </ul>
          <p className="text-2xs leading-relaxed text-ink-faint">{SKIP_WHY[reason]}</p>
        </div>
      ))}
    </div>
  );
}

const SKIP_TITLE: Record<IntakeSkip["reason"], string> = {
  too_large: "너무 큰 파일",
  binary: "텍스트가 아닌 파일",
};

const SKIP_WHY: Record<IntakeSkip["reason"], string> = {
  too_large:
    "한 파일 50MB까지만 받습니다. 이만한 파일은 대개 생성된 산출물이고, 검사는 1.5MB가 넘는 파일을 어차피 읽지 않습니다.",
  binary:
    "이미지나 실행 파일처럼 텍스트가 아닌 것은 읽지 않습니다. 그대로 담아 두면 ‘수정된 소스’ 를 내려받을 때 깨진 파일이 나오기 때문에, 아예 넣지 않습니다.",
};

/** MB below a megabyte reads as `0MB`, which looks like a bug rather than a size. */
function size(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(0)}MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${bytes}B`;
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="text-ink-faint">{label}</dt>
      <dd className="text-ink-strong">{(value ?? 0).toLocaleString()}</dd>
    </div>
  );
}
