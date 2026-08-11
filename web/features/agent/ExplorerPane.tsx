"use client";

import { useEffect, useMemo } from "react";

import { fromAgent } from "@/lib/model/finding";
import { scanningFiles } from "@/lib/run/reduce";
import { useDeleteFile, useDeleteRun, useFiles, useFindings } from "@/lib/run/queries";
import { useCreateFile, useUploadTree } from "@/lib/run/new-file";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";
import FileExplorer from "./FileExplorer";
import { coverageOf } from "./RunSummary";
import { useOpenFile } from "@/lib/run/selection";

/**
 * The explorer, and the run it belongs to.
 *
 * Creating a run is lazy: pasting one snippet should not require uploading
 * something first, so the first write makes the run if there is not one yet.
 */
export default function ExplorerPane() {
  const [runId, setRunId] = useRunId();
  const [path, setPath] = useOpenFile();

  const files = useFiles(runId);
  const findings = useFindings(runId);
  const newFile = useCreateFile();
  const upload = useUploadTree();
  const remove = useDeleteFile(runId);
  const clear = useDeleteRun();

  const list = useMemo(() => files.data ?? [], [files.data]);
  const ui = useMemo(() => fromAgent(findings.data?.findings ?? []), [findings.data]);

  const { live, phase } = useRunStream();
  const progress = useMemo(() => {
    const { total, done } = coverageOf(findings.data?.stats, live);
    return {
      scanning: scanningFiles(live),
      scanned: live.scanned,
      live: phase === "running" || phase === "starting" || phase === "paused",
      done,
      total,
    };
  }, [findings.data, live, phase]);

  // Open something rather than nothing: an explorer with files and an empty
  // editor beside it looks broken.
  useEffect(() => {
    if (path || list.length === 0) return;
    const first = list.find((each) => /\.(c|h|cpp|cc|hpp|java|py|ts|go|rs)$/i.test(each)) ?? list[0];
    void setPath(first);
  }, [path, list, setPath]);

  return (
    <FileExplorer
      files={list}
      active={path}
      findings={ui}
      progress={progress}
      busy={newFile.busy || upload.busy}
      onOpen={(next) => void setPath(next)}
      onCreate={(name) => void newFile.create(name)}
      onDelete={(target) => {
        remove.mutate(target, {
          onSuccess: (result) => {
            if (path === target) void setPath(result.files[0] ?? null);
          },
        });
      }}
      onUpload={upload.send}
      onClear={
        runId
          ? () =>
              clear.mutate(runId, {
                onSuccess: () => {
                  // Back to an empty workbench rather than to a run id that
                  // now 404s on every query the page makes.
                  setRunId(null);
                  void setPath(null);
                },
              })
          : undefined
      }
    />
  );
}
