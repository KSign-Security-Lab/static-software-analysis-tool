"use client";

import { UserRound } from "lucide-react";
import { useState, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { keys } from "@/lib/query/keys";
import { MAX_NAME, normalise, readOwner, subscribe, writeOwner } from "@/lib/run/whoami";

/**
 * Whose runs 지난 검사 shows.
 *
 * **Not a login**, and the copy says so rather than leaving it to be assumed:
 * nothing is challenged, and a run stays readable by id whoever asks. It exists
 * because the server is shared and a list of every scan on the box is mostly
 * other people's and useless.
 *
 * Reads through `useSyncExternalStore` because the header here and every request
 * in `lib/api/client` read the same `localStorage` value, and they are not in one
 * tree.
 */
export default function WhoAmI() {
  const owner = useSyncExternalStore(subscribe, readOwner, () => null);
  const [draft, setDraft] = useState("");
  const [open, setOpen] = useState(false);
  const client = useQueryClient();

  function commit() {
    writeOwner(draft);
    setOpen(false);
    // The list is filtered server-side by the header, so a new name is a new
    // list rather than the same one re-sorted.
    void client.invalidateQueries({ queryKey: keys.runs() });
  }

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setDraft(owner ?? "");
      }}
    >
      <PopoverTrigger asChild>
        <Button size="sm" variant="ghost">
          <UserRound className="size-3.5" />
          {owner ?? "이름 없음"}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 space-y-2">
        <p className="text-xs text-ink-muted">
          이름을 적으면 ‘지난 검사’ 가 내가 한 것만 보여 줍니다.
        </p>
        <p className="text-2xs leading-relaxed text-ink-faint">
          로그인이 아닙니다. 확인하지 않고, 막지도 않습니다 — 공용 서버에서 남의 검사가 목록에 섞이지 않게 하는 것이
          전부입니다.
        </p>
        <form
          className="flex gap-1.5"
          onSubmit={(event) => {
            event.preventDefault();
            commit();
          }}
        >
          <Input
            value={draft}
            onChange={(event) => setDraft(normalise(event.target.value))}
            maxLength={MAX_NAME}
            placeholder="이름"
            aria-label="이름"
            autoFocus
          />
          <Button type="submit" size="sm">
            저장
          </Button>
        </form>
      </PopoverContent>
    </Popover>
  );
}
