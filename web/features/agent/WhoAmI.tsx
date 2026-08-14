"use client";

import { useState, useSyncExternalStore } from "react";
import { UserRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useQueryClient } from "@tanstack/react-query";
import { keys } from "@/lib/query/keys";
import { MAX_NAME, normalise, readOwner, subscribe, writeOwner } from "@/lib/run/whoami";

/**
 * Who is using this browser -- asked once, changeable from the bar.
 *
 * **Not a login.** Nothing checks it, nothing is hidden from anyone who has a
 * run id, and any name can be typed. It is here because the server is shared:
 * 지난 검사 was a list of every scan on the box, most of them somebody else's,
 * and there was no way to tell which. See `lib/run/whoami`.
 *
 * The dialog opens itself on a first visit rather than waiting to be found. A
 * name given later would not retro-label the runs already made without it, so
 * asking up front is the only version of this that works.
 */
export default function WhoAmI() {
  const owner = useSyncExternalStore(subscribe, readOwner, () => null);
  // Whether this is the browser rather than the server render. `readOwner`
  // reads localStorage, so the first pass has to agree with the server -- and
  // that is the pass that must not decide the dialog is open.
  const hydrated = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  // null while nobody has said: then the answer is "open if there is no name".
  // Held this way rather than set from an effect, which is a cascading render.
  const [decided, setDecided] = useState<boolean | null>(null);
  const [draft, setDraft] = useState("");
  const client = useQueryClient();

  const open = decided ?? (hydrated && owner === null);

  function show() {
    setDraft(owner ?? "");
    setDecided(true);
  }

  function save() {
    const name = normalise(draft);
    if (!name) return;
    writeOwner(name);
    setDecided(false);
    // The run list is filtered by this, so it is a different list now.
    client.invalidateQueries({ queryKey: keys.runs() });
  }

  return (
    <>
      <Button size="xs" variant="ghost" className="text-ink-muted" onClick={show} title="이름 바꾸기">
        <UserRound />
        {owner ?? "이름 없음"}
      </Button>

      <Dialog open={open} onOpenChange={setDecided}>
        <DialogContent className="sm:max-w-100">
          <DialogHeader>
            <DialogTitle>이름을 알려주세요</DialogTitle>
            <DialogDescription>
              이 서버는 여러 사람이 함께 씁니다. 지난 검사 목록에서 내 검사만 보이게 하는 데만
              씁니다. 로그인이 아니고, 아무것도 잠그지 않습니다.
            </DialogDescription>
          </DialogHeader>

          <Input
            autoFocus
            value={draft}
            maxLength={MAX_NAME}
            placeholder="예: keonoh"
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") save();
            }}
          />

          <DialogFooter>
            {/* Closing without a name is allowed and means anonymous -- the
                CLI has no name either, and the API serves a request without
                the header rather than refusing it. */}
            <Button variant="ghost" onClick={() => setDecided(false)}>
              그만두기
            </Button>
            <Button onClick={save} disabled={!normalise(draft)}>
              저장
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
