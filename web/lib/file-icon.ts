import { Braces, FileCode, FileJson, FileText, Hash, Settings2, type LucideIcon } from "lucide-react";

/**
 * A glyph and a colour per kind of file.
 *
 * Every row in the tree drew the same `FileCode` at 60% opacity, so a C source,
 * its header, a README and a lockfile were four identical grey lines differing
 * only in their text -- and a file tree is scanned by shape and colour long
 * before it is read.
 *
 * The colour is the half that does the work, and it is why this returns a tone
 * rather than only an icon: six monochrome glyphs at the size a tree row allows
 * are six smudges. Tokens rather than raw colours, so the tree stays in the same
 * palette as everything else and follows the theme.
 *
 * Grouped by what the reader is about to do with the file rather than by
 * language family: source you inspect, a header you follow, data you skim,
 * config you rarely open.
 */
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

/** Falls back rather than exhausts: an unknown language should still look like a file. */
export function glyphForFile(path: string): FileGlyph {
  const name = path.split("/").pop() ?? path;
  // A dotfile is all extension and no name -- `.env`, `.gitignore` -- and
  // splitting it the usual way gives an empty stem and the wrong lookup.
  const extension = name.startsWith(".") ? name.slice(1) : (name.split(".").pop() ?? "");
  return BY_EXTENSION[extension.toLowerCase()] ?? { icon: Braces, tone: "text-ink-faint" };
}
