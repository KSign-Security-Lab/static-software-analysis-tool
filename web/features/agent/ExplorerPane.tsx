"use client";

import { useEffect, useMemo } from "react";

import { fromAgent } from "@/lib/model/finding";
import { useDeleteFile, useFiles, useFindings, useUpload } from "@/lib/run/queries";
import { useCreateFile } from "@/lib/run/new-file";
import { useRunId } from "@/lib/run/use-run-id";
import FileExplorer from "./FileExplorer";
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
  const upload = useUpload();
  const remove = useDeleteFile(runId);

  const list = useMemo(() => files.data ?? [], [files.data]);
  const ui = useMemo(() => fromAgent(findings.data?.findings ?? []), [findings.data]);

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
      busy={newFile.busy || upload.isPending}
      onOpen={(next) => void setPath(next)}
      onCreate={(name) => void newFile.create(name)}
      onDelete={(target) => {
        remove.mutate(target, {
          onSuccess: (result) => {
            if (path === target) void setPath(result.files[0] ?? null);
          },
        });
      }}
      onUpload={(picked) =>
        upload.mutate(picked, {
          onSuccess: (result) => {
            setRunId(result.run_id);
            void setPath(null);
          },
        })
      }
    />
  );
}
