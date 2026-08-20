"use client";

import { AlertTriangle, FileArchive, FolderGit2, FolderOpen, Loader2, Play, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { RunSummary, UploadResult } from "@/lib/api/types";
import { filesFromDrop } from "@/lib/run/drop";
import { useCloneRepo, useStartRun, useUpload, useUploadArchive } from "@/lib/run/queries";
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

  // The run row is the truth once it exists; `uploaded` is only what this tab
  // just did, and it carries the one thing the row does not: how much was read.
  const indexed = uploaded?.run_id === runId ? uploaded : null;

  function accept(result: UploadResult) {
    setUploaded(result);
    setRunId(result.run_id);
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <div className="mx-auto w-full max-w-2xl px-6 py-10">
        <h1 className="text-lg font-semibold text-ink-strong">검사할 코드</h1>
        <p className="mt-1 text-xs leading-relaxed text-ink-muted">
          폴더, 압축 파일, git 주소 가운데 하나를 주십시오. 읽고 나면 무엇을 얼마나 읽었는지 먼저 보여 드립니다.
        </p>

        {run?.status === "failed" && run.error && (
          <p className="mt-4 flex items-start gap-2 rounded-md border border-danger/40 bg-danger-wash px-3 py-2 text-xs text-ink">
            <AlertTriangle className="mt-px size-3.5 shrink-0 text-danger" aria-hidden />
            {run.error}
          </p>
        )}

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
            <FolderIntake onDone={accept} />
          </TabsContent>
          <TabsContent value="zip">
            <ArchiveIntake onDone={accept} />
          </TabsContent>
          <TabsContent value="git">
            <GitIntake onDone={accept} />
          </TabsContent>
        </Tabs>

        {runId && <Ready run={run} indexed={indexed} />}
      </div>
    </div>
  );
}

/* -- the three ways in -------------------------------------------------------- */

function FolderIntake({ onDone }: { onDone: (result: UploadResult) => void }) {
  const upload = useUpload();
  const picker = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(0);

  async function send(files: (File | { file: File; path: string })[]) {
    if (files.length === 0) return;
    onDone(await upload.mutateAsync(files));
  }

  return (
    <div
      // Depth-counted: `dragleave` fires on every child the pointer crosses, so
      // a boolean flickers off over the text inside the zone it is describing.
      onDragEnter={(event) => {
        event.preventDefault();
        setOver((n) => n + 1);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => setOver((n) => Math.max(0, n - 1))}
      onDrop={(event) => {
        event.preventDefault();
        setOver(0);
        void filesFromDrop(event.dataTransfer).then((dropped) => send(dropped));
      }}
      className={cn(
        "mt-3 grid place-items-center gap-3 rounded-lg border border-dashed border-line-2 px-6 py-12 text-center transition-colors",
        over > 0 && "border-accent bg-accent-wash",
      )}
    >
      <Upload className={cn("size-6", over > 0 ? "text-accent-ink" : "text-ink-faint")} aria-hidden />
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
      <Button variant="outline" size="sm" disabled={upload.isPending} onClick={() => picker.current?.click()}>
        {upload.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <FolderOpen className="size-3.5" />}
        폴더 고르기
      </Button>
      <p className="text-2xs text-ink-faint">
        하위 폴더까지 그대로 올라갑니다. <code className="font-mono">node_modules</code> 같은 것은 검사에서 건너뜁니다.
      </p>
    </div>
  );
}

function ArchiveIntake({ onDone }: { onDone: (result: UploadResult) => void }) {
  const upload = useUploadArchive();
  const picker = useRef<HTMLInputElement>(null);

  return (
    <div className="mt-3 grid place-items-center gap-3 rounded-lg border border-dashed border-line-2 px-6 py-12 text-center">
      <FileArchive className="size-6 text-ink-faint" aria-hidden />
      <p className="text-sm text-ink-muted">.zip 파일을 고르세요</p>
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
      <Button variant="outline" size="sm" disabled={upload.isPending} onClick={() => picker.current?.click()}>
        {upload.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <FileArchive className="size-3.5" />}
        압축 파일 고르기
      </Button>
      <p className="text-2xs text-ink-faint">500MB, 20,000개 파일까지. 한 파일은 50MB까지.</p>
    </div>
  );
}

function GitIntake({ onDone }: { onDone: (result: UploadResult) => void }) {
  const clone = useCloneRepo();
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
      <Button type="submit" size="sm" disabled={!url.trim() || clone.isPending}>
        {clone.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <FolderGit2 className="size-3.5" />}
        가져오기
      </Button>
      <p className="text-2xs leading-relaxed text-ink-faint">
        공개 저장소만, https 주소만 가져옵니다. 주소에 토큰을 넣지 마십시오 — 이 주소는 검사 기록에 그대로 남습니다.
        가져온 검사는 나중에 고친 것을 브랜치로 바로 올릴 수 있습니다.
      </p>
    </form>
  );
}

/* -- what arrived, and the one button ----------------------------------------- */

function Ready({ run, indexed }: { run: RunSummary | undefined; indexed: UploadResult | null }) {
  const [runId] = useRunId();
  const { ensureAttached } = useRunStream();
  const start = useStartRun(runId, ensureAttached);
  const stats = indexed?.index ?? run?.index;
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
            disabled={!runId || start.isPending || stats?.chunks === 0}
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

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="text-ink-faint">{label}</dt>
      <dd className="text-ink-strong">{(value ?? 0).toLocaleString()}</dd>
    </div>
  );
}
