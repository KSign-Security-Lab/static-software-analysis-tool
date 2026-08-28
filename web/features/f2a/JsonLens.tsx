"use client";

import { Copy } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

/**
 * The raw result.
 *
 * Deliberately a <pre> and not a collapsible tree: this exists for checking
 * what the pipeline actually emitted, and a tree that hides half of it by
 * default is the opposite of that.
 */
export default function JsonLens({ value }: { value: unknown }) {
  const text = JSON.stringify(value, null, 2);

  return (
    <div className="relative h-full">
      <Button
        size="xs"
        variant="outline"
        className="absolute top-2 right-3 z-10"
        onClick={() => {
          void navigator.clipboard.writeText(text);
          toast.success("복사했습니다");
        }}
      >
        <Copy />
        복사
      </Button>
      <pre className="h-full overflow-auto p-3 font-mono text-2xs leading-relaxed text-ink-muted">{text}</pre>
    </div>
  );
}
