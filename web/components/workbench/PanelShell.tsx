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
        <header className="flex h-9 shrink-0 items-center gap-2 border-b border-line px-2.5">
          {/* Not uppercase. Korean has no case, so it only ever shouted the
              Latin ones -- and it cost the title the shape a reader scans by. */}
          {title && <h2 className="shrink-0 truncate text-xs font-semibold text-ink-strong">{title}</h2>}
          {note && <span className="truncate text-2xs text-ink-faint">{note}</span>}
          {actions && <div className="ml-auto flex items-center gap-1">{actions}</div>}
        </header>
      )}
      <div className={cn("min-h-0 flex-1 overflow-auto", bodyClassName)}>{children}</div>
    </section>
  );
}

/**
 * A panel with nothing in it yet, and what would put something there.
 *
 * Anchored to the top rather than centred. These panels are as tall as the
 * window, so centring put one grey sentence at the vertical middle of eight
 * hundred empty pixels -- which reads as a void with a caption rather than as
 * a panel waiting for input. Against the top it reads as a placeholder, and
 * the eye finds it where it looks for everything else.
 */
export function EmptyState({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-2 px-3 py-4">
      <span className="grid size-8 place-items-center rounded-md bg-surface-2 text-ink-faint">
        <Icon className="size-4" />
      </span>
      <p className="text-sm font-medium text-ink-muted">{title}</p>
      {children && <p className="max-w-72 text-xs leading-relaxed text-ink-faint">{children}</p>}
    </div>
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
