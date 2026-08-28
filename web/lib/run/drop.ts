/**
 * A dropped folder, as a list of files with the paths they had in it.
 *
 * `<input type="file" webkitdirectory>` sets `webkitRelativePath` on everything
 * it hands over, and `uploadSource` reads it. A drop does not: the `File`
 * objects that come out of a `DataTransfer` know their own name and nothing
 * about the directory they were in, so dropping a tree uploaded a flat pile of
 * basenames -- and two `main.c` in two directories collided into one.
 *
 * The entries API is the only way to walk what was dropped. It is prefixed
 * (`webkitGetAsEntry`) in every engine that has it, and standardised nowhere,
 * which is why the types below are declared here rather than imported.
 */

export interface DroppedFile {
  file: File;
  /** Relative to the drop, e.g. `src/net/handler.c`. */
  path: string;
}

interface FileSystemEntryLike {
  isFile: boolean;
  isDirectory: boolean;
  name: string;
  file?: (onSuccess: (file: File) => void, onError: (error: unknown) => void) => void;
  createReader?: () => {
    readEntries: (onSuccess: (entries: FileSystemEntryLike[]) => void, onError: (error: unknown) => void) => void;
  };
}

/** Refuse to walk for ever: a dropped `node_modules` is not a scan target. */
const MAX_FILES = 20_000;
const MAX_DEPTH = 32;

/**
 * Directories not worth reading off the reader's disk.
 *
 * The comment above has said `node_modules` is not a scan target since this file
 * was written, and nothing acted on it: the walk read every object in `.git` into
 * browser memory, uploaded it, and the server discarded it -- which is most of
 * why dropping a real project was slow enough to look broken.
 *
 * Must stay a **subset** of `SKIP_DIRS` in `packages/agent/src/agent/files.py`.
 * Skipping something the server would have kept makes files vanish silently;
 * keeping something the server discards only costs bandwidth. So when the two
 * drift, drift this way.
 */
const SKIP_DIRS = new Set([
  ".git",
  ".hg",
  ".svn",
  "node_modules",
  "__pycache__",
  ".venv",
  "venv",
  "dist",
  "build",
  "target",
  ".next",
  ".mypy_cache",
  ".pytest_cache",
  ".ruff_cache",
  "vendor",
  "third_party",
]);

function fileOf(entry: FileSystemEntryLike): Promise<File | null> {
  if (!entry.file) return Promise.resolve(null);
  return new Promise((resolve) => entry.file!(resolve, () => resolve(null)));
}

/**
 * One directory's entries.
 *
 * `readEntries` returns at most a hundred at a time and signals the end with an
 * empty batch, so a single call silently truncates any directory bigger than
 * that -- which is the sort of bug that only shows up on somebody else's repo.
 */
async function entriesOf(entry: FileSystemEntryLike): Promise<FileSystemEntryLike[]> {
  const reader = entry.createReader?.();
  if (!reader) return [];

  const all: FileSystemEntryLike[] = [];
  for (;;) {
    const batch = await new Promise<FileSystemEntryLike[]>((resolve) =>
      reader.readEntries(resolve, () => resolve([])),
    );
    if (batch.length === 0) return all;
    all.push(...batch);
  }
}

async function walk(entry: FileSystemEntryLike, prefix: string, out: DroppedFile[], depth: number): Promise<void> {
  if (out.length >= MAX_FILES || depth > MAX_DEPTH) return;
  // Before the path is built, so the directory is never descended into.
  if (entry.isDirectory && SKIP_DIRS.has(entry.name)) return;
  const path = prefix ? `${prefix}/${entry.name}` : entry.name;

  if (entry.isFile) {
    const file = await fileOf(entry);
    if (file) out.push({ file, path });
    return;
  }

  if (entry.isDirectory) {
    for (const child of await entriesOf(entry)) {
      await walk(child, path, out, depth + 1);
      if (out.length >= MAX_FILES) return;
    }
  }
}

/**
 * What was dropped, with paths.
 *
 * `dataTransfer.items` has to be read synchronously -- it is emptied as soon as
 * the drop handler returns -- so every entry is taken out first and only then
 * walked. Falls back to `dataTransfer.files` where the entries API is missing,
 * which loses directory structure but still accepts a handful of dropped files.
 */
/**
 * Whether a drop is a single archive rather than a tree.
 *
 * A bare `.zip` goes to the archive endpoint and a tree goes to the multipart
 * one, so the drop handler has to tell them apart -- and one `.zip` *inside* a
 * dropped folder is a tree with one file in it, not an archive upload. Hence the
 * path check: a bare drop has no directory in front of its name.
 */
export function isArchiveDrop(dropped: DroppedFile[]): boolean {
  if (dropped.length !== 1) return false;
  const only = dropped[0];
  return only.path === only.file.name && /\.zip$/i.test(only.file.name);
}

export async function filesFromDrop(transfer: DataTransfer): Promise<DroppedFile[]> {
  const entries = Array.from(transfer.items)
    .filter((item) => item.kind === "file")
    .map((item) => (item as unknown as { webkitGetAsEntry?: () => FileSystemEntryLike | null }).webkitGetAsEntry?.())
    .filter((entry): entry is FileSystemEntryLike => Boolean(entry));

  if (entries.length === 0) {
    return Array.from(transfer.files).map((file) => ({ file, path: file.webkitRelativePath || file.name }));
  }

  const out: DroppedFile[] = [];
  for (const entry of entries) await walk(entry, "", out, 0);
  return out;
}
