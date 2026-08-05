import { cn } from "@/lib/utils";

/**
 * A titled region inside a panel: a thin header strip and a scrolling body.
 *
 * Every panel in the workbench has the same anatomy, and the height of that
 * header being identical everywhere is most of what makes the layout read as
 * one application rather than four.
 */
export function PanelShell({
  title,
  note,
  actions,
  className,
  bodyClassName,
  children,
}: {
  title?: React.ReactNode;
  note?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("flex h-full min-h-0 flex-col bg-surface", className)}>
      {(title || actions) && (
        <header className="flex h-8 shrink-0 items-center gap-2 border-b border-line px-2.5">
          {title && (
            <h2 className="truncate text-2xs font-semibold tracking-wide text-ink-muted uppercase">{title}</h2>
          )}
          {note && <span className="truncate text-2xs text-ink-faint">{note}</span>}
          {actions && <div className="ml-auto flex items-center gap-1">{actions}</div>}
        </header>
      )}
      <div className={cn("min-h-0 flex-1 overflow-auto", bodyClassName)}>{children}</div>
    </section>
  );
}

/** Not built yet. Says which commit fills it in, so it reads as staging. */
export function Placeholder({ what }: { what: string }) {
  return (
    <div className="grid h-full place-items-center p-6 text-center">
      <p className="max-w-72 text-sm text-ink-faint">
        {what}
        <span className="mt-1 block text-2xs">준비 중</span>
      </p>
    </div>
  );
}
