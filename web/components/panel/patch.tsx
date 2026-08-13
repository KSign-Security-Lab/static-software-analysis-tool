import { cn } from "@/lib/utils";

/**
 * A proposed change, as a patch.
 *
 * The `---` and `+++` lines are dropped. They name a file the reader is looking
 * at, in a pane attached to that file, above a hunk header that gives the line --
 * three lines of a five-line patch spent on where it applies, which was never in
 * doubt.
 *
 * Not Monaco. `components/editor/DiffView.tsx` exists for the side-by-side view a
 * span replay needs; loading an editor to show four lines of change inside a card
 * is the wrong size of tool, and the two are kept apart deliberately rather than
 * by neglect.
 */
export function Patch({ diff, className }: { diff: string; className?: string }) {
  const lines = diff
    .split("\n")
    .filter((line) => !line.startsWith("--- ") && !line.startsWith("+++ "))
    .filter((line, index, all) => line !== "" || index < all.length - 1);

  return (
    <pre
      className={cn(
        "overflow-x-auto rounded-md border border-line bg-field p-2 font-mono text-2xs leading-relaxed",
        className,
      )}
    >
      {lines.map((line, index) => (
        <span
          key={index}
          className={cn(
            "block",
            line.startsWith("+") && "text-ok",
            line.startsWith("-") && "text-danger",
            line.startsWith("@@") && "text-ink-faint",
          )}
        >
          {line || " "}
        </span>
      ))}
    </pre>
  );
}
