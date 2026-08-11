"use client";

import { FileCode, FilePlus, FolderUp, Trash2 } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { PanelShell } from "@/components/workbench/PanelShell";
import { SEVERITY_DOT, SEVERITY_LABEL, countByFile, type UiFinding } from "@/lib/model/finding";
import { cn } from "@/lib/utils";

/**
 * A new file's name, validated before it is sent.
 *
 * The old flow was `window.prompt`, and its result went unchecked into
 * `PUT /file` -- so `../../etc/passwd` was accepted by the UI and refused only
 * by the server's path resolver. A dialog is where that check belongs, and it
 * can say why rather than failing with a 400.
 */
export function validateName(name: string, existing: string[]): string | null {
  const trimmed = name.trim();
  if (!trimmed) return "이름을 입력하세요.";
  if (trimmed.startsWith("/")) return "절대 경로는 쓸 수 없습니다.";
  if (trimmed.split("/").some((part) => part === "..")) return "상위 디렉터리로 나갈 수 없습니다.";
  if (/[\\:*?"<>|]/.test(trimmed)) return '\\ : * ? " < > | 는 쓸 수 없습니다.';
  if (trimmed.endsWith("/")) return "디렉터리가 아니라 파일 이름이어야 합니다.";
  if (existing.includes(trimmed)) return "같은 이름의 파일이 이미 있습니다.";
  return null;
}

export default function FileExplorer({
  files,
  active,
  findings,
  progress,
  busy,
  onOpen,
  onCreate,
  onDelete,
  onUpload,
}: {
  files: string[];
  active: string | null;
  findings: UiFinding[];
  /**
   * Where the run has got to, while one is going.
   *
   * The explorer is looking straight at the thing being scanned and used to say
   * nothing about it for the several minutes that took, so a run in flight was
   * visible only as a word in a pane on the far side of the window.
   */
  progress?: {
    scanning: Set<string>;
    scanned: Set<string>;
    /** Whether a run is in flight; without one, "not reached" means nothing. */
    live: boolean;
    done: number;
    total: number;
  };
  busy?: boolean;
  onOpen: (path: string) => void;
  onCreate: (path: string) => void;
  onDelete: (path: string) => void;
  onUpload: (files: File[]) => void;
}) {
  const counts = useMemo(() => countByFile(findings), [findings]);
  const input = useRef<HTMLInputElement>(null);

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);

  const problem = creating ? validateName(name, files) : null;
  const canCreate = name.trim().length > 0 && !problem;

  const ordered = useMemo(() => {
    // Worst first, so the file that needs attention is not below the fold.
    const rank = (path: string) => {
      const worst = counts.get(path)?.worst;
      return worst ? ["critical", "high", "medium", "low", "info"].indexOf(worst) : 9;
    };
    return [...files].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
  }, [files, counts]);

  const body = (
    <>
      {ordered.length === 0 ? (
        <p className="p-3 text-2xs leading-relaxed text-ink-faint">
          아직 파일이 없습니다. 붙여넣거나, 파일을 추가하거나, 트리를 업로드하세요.
        </p>
      ) : (
        <ul className="py-1">
          {ordered.map((path) => {
            const count = counts.get(path);
            const scanning = progress?.scanning.has(path) ?? false;
            // Dimmed only while a run is actually going: otherwise every file
            // in a run that has never been inspected would read as skipped.
            const waiting = Boolean(progress?.live) && !scanning && !progress?.scanned.has(path);
            return (
              <li key={path} className="group/file relative">
                <button
                  type="button"
                  onClick={() => onOpen(path)}
                  className={cn(
                    "flex w-full items-center gap-1.5 border-l-2 py-1.5 pr-7 pl-2 text-left text-xs transition-colors",
                    "hover:bg-surface-2",
                    // Selection is a marker and a weight, not a coloured slab
                    // running the width of the panel: an open file is a place
                    // you are, not a result you were meant to look at.
                    active === path
                      ? "border-l-accent bg-surface-2 font-medium text-ink-strong"
                      : "border-l-transparent text-ink-muted",
                    waiting && "opacity-55",
                  )}
                >
                  <FileCode className={cn("size-3.5 shrink-0 opacity-60", scanning && "text-accent-ink opacity-100")} />
                  <span className="truncate">{path}</span>
                  <span className="ml-auto flex shrink-0 items-center gap-1 pr-0.5">
                    {scanning && (
                      <span
                        title="검사 중"
                        aria-label="검사 중"
                        className="size-1.5 animate-pulse rounded-full bg-accent"
                      />
                    )}
                    {count && (
                      <span
                        className="flex items-center gap-1"
                        title={`${SEVERITY_LABEL[count.worst ?? "info"]} · ${count.total}건`}
                      >
                        <span className={cn("size-1.5 rounded-full", SEVERITY_DOT[count.worst ?? "info"])} />
                        <span className="font-mono text-2xs">{count.total}</span>
                      </span>
                    )}
                  </span>
                </button>
                <button
                  type="button"
                  aria-label={`${path} 삭제`}
                  onClick={() => setDeleting(path)}
                  className="absolute top-1/2 right-1 hidden -translate-y-1/2 rounded-xs p-0.5 text-ink-faint hover:bg-danger-wash hover:text-danger group-hover/file:block"
                >
                  <Trash2 className="size-3" />
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (!canCreate) return;
              onCreate(name.trim());
              setName("");
              setCreating(false);
            }}
          >
            <DialogHeader>
              <DialogTitle>새 파일</DialogTitle>
              <DialogDescription>실행 안에서의 상대 경로입니다. 디렉터리는 자동으로 만들어집니다.</DialogDescription>
            </DialogHeader>
            <div className="my-4 space-y-2">
              <Label htmlFor="new-file-name">경로</Label>
              <Input
                id="new-file-name"
                autoFocus
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="src/main.c"
                aria-invalid={Boolean(problem)}
                aria-describedby={problem ? "new-file-problem" : undefined}
              />
              {problem && (
                <p id="new-file-problem" className="text-2xs text-danger">
                  {problem}
                </p>
              )}
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setCreating(false)}>
                취소
              </Button>
              <Button type="submit" disabled={!canCreate}>
                만들기
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{deleting} 을(를) 삭제할까요?</AlertDialogTitle>
            <AlertDialogDescription>
              파일과 그 파일에서 나온 결과가 함께 사라집니다. 되돌릴 수 없습니다.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              onClick={() => {
                if (deleting) onDelete(deleting);
                setDeleting(null);
              }}
            >
              삭제
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );

  return (
    <PanelShell
      title="탐색기"
      note={
        progress?.live && progress.total > 0
          ? `${files.length}개 파일 · 단위 ${progress.done}/${progress.total}`
          : files.length
            ? `${files.length}개 파일`
            : "검사할 파일을 여기에 넣습니다"
      }
      actions={
        <>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-xs" onClick={() => setCreating(true)} disabled={busy} aria-label="새 파일">
                <FilePlus />
              </Button>
            </TooltipTrigger>
            <TooltipContent>새 파일 ⌘N</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-xs" onClick={() => input.current?.click()} disabled={busy} aria-label="트리 업로드">
                <FolderUp />
              </Button>
            </TooltipTrigger>
            <TooltipContent>트리 업로드</TooltipContent>
          </Tooltip>
          {/* `webkitdirectory`, which this said it did and did not do: without
              it the picker offers files, every one of them arrives with an empty
              `webkitRelativePath`, and a tree lands as a pile of basenames. */}
          <input
            ref={input}
            type="file"
            multiple
            hidden
            {...{ webkitdirectory: "" }}
            onChange={(event) => {
              const picked = Array.from(event.target.files ?? []);
              if (picked.length) onUpload(picked);
              event.target.value = "";
            }}
          />
        </>
      }
    >
      {body}
    </PanelShell>
  );
}
