import { Braces, FileCode, FileJson, FileText, Hash, Settings2, type LucideIcon } from "lucide-react";

export interface FileGlyph {
  icon: LucideIcon;
  tone: string;
}

const SOURCE: FileGlyph = { icon: FileCode, tone: "text-accent-ink" };
const HEADER: FileGlyph = { icon: Hash, tone: "text-alt" };
const DATA: FileGlyph = { icon: FileJson, tone: "text-warn" };
const CONFIG: FileGlyph = { icon: Settings2, tone: "text-ink-muted" };
const DOC: FileGlyph = { icon: FileText, tone: "text-ok" };

const BY_EXTENSION: Record<string, FileGlyph> = {
  c: SOURCE,
  cc: SOURCE,
  cpp: SOURCE,
  cxx: SOURCE,
  go: SOURCE,
  java: SOURCE,
  js: SOURCE,
  jsx: SOURCE,
  py: SOURCE,
  rs: SOURCE,
  ts: SOURCE,
  tsx: SOURCE,

  h: HEADER,
  hh: HEADER,
  hpp: HEADER,

  json: DATA,
  lock: DATA,

  cfg: CONFIG,
  conf: CONFIG,
  env: CONFIG,
  ini: CONFIG,
  toml: CONFIG,
  yaml: CONFIG,
  yml: CONFIG,

  md: DOC,
  rst: DOC,
  txt: DOC,
};

export function glyphForFile(path: string): FileGlyph {
  const name = path.split("/").pop() ?? path;
  const extension = name.startsWith(".") ? name.slice(1) : (name.split(".").pop() ?? "");
  return BY_EXTENSION[extension.toLowerCase()] ?? { icon: Braces, tone: "text-ink-faint" };
}
