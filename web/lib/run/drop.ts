export interface DroppedFile {
  file: File;
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

const MAX_FILES = 20_000;
const MAX_DEPTH = 32;

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
