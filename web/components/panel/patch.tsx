import { cn } from "@/lib/utils";

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
