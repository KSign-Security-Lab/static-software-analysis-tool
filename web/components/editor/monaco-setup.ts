import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";

import { installClipboardFallback } from "./clipboard-fallback";

let configured = false;

export function setupMonaco(): typeof monaco {
  if (configured) return monaco;
  configured = true;

  installClipboardFallback();

  loader.config({ monaco });

  self.MonacoEnvironment = {
    getWorker: (_workerId: string, label: string) =>
      label === "json"
        ? new Worker(new URL("./json.worker.ts", import.meta.url), { type: "module" })
        : new Worker(new URL("./monaco.worker.ts", import.meta.url), { type: "module" }),
  };

  return monaco;
}

setupMonaco();
