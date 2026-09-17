import { cn } from "@/lib/utils";

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
          {title && <h2 className="min-w-0 truncate text-xs font-semibold text-ink-strong">{title}</h2>}
          {note && <span className="min-w-0 shrink-[100] truncate text-2xs text-ink-faint">{note}</span>}
          {actions && <div className="ml-auto flex shrink-0 items-center gap-1">{actions}</div>}
        </header>
      )}
      <div className={cn("min-h-0 flex-1 overflow-auto", bodyClassName)}>{children}</div>
    </section>
  );
}

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
