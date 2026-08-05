"use client";

import { useMemo } from "react";

import StepCard, { type Format, type Granularity } from "./StepCard";
import type { Checkpoint } from "@/lib/api/studio";
import { byId, changedKeys, lanesOf } from "@/lib/studio/lanes";

/**
 * Every super-step the run has taken, and what each one wrote.
 *
 * The controls decide how much of a step is shown; the steps below them carry
 * the edit-and-fork. Forks are indented onto their own line, because a branch is
 * a different course and not a later step on the same one.
 */

const GRANULARITY: Record<Granularity, string> = { 0: "간략", 1: "보통", 2: "전체" };

export default function ThreadPanel({
  checkpoints,
  selected,
  onSelectStep,
  granularity,
  onGranularity,
  format,
  onFormat,
  onFork,
  onRerun,
  loadFull,
  busy,
  interrupted,
}: {
  checkpoints: Checkpoint[];
  selected: string | null;
  onSelectStep: (checkpointId: string) => void;
  granularity: Granularity;
  onGranularity: (value: Granularity) => void;
  format: Format;
  onFormat: (value: Format) => void;
  onFork: (checkpointId: string, values: Record<string, unknown>) => void;
  onRerun: (checkpointId: string) => void;
  loadFull: (checkpointId: string) => Promise<Record<string, unknown>>;
  busy: boolean;
  interrupted: boolean;
}) {
  const lanes = useMemo(() => lanesOf(checkpoints), [checkpoints]);
  const parents = useMemo(() => byId(checkpoints), [checkpoints]);

  return (
    <section className="sx-thread-pane">
      <div className="sx-thread-controls">
        <input
          type="range"
          className="sx-slider"
          min={0}
          max={2}
          step={1}
          value={granularity}
          aria-label="정보 밀도"
          onChange={(event) => onGranularity(Number(event.target.value) as Granularity)}
        />
        <span className="sx-slider-label">{GRANULARITY[granularity]}</span>

        <div className="sx-seg">
          {(["pretty", "json"] as const).map((value) => (
            <button
              key={value}
              type="button"
              className={`sx-seg-btn ${format === value ? "is-on" : ""}`}
              onClick={() => onFormat(value)}
            >
              {value === "pretty" ? "Pretty" : "JSON"}
            </button>
          ))}
        </div>
      </div>

      <div className="sx-steps">
        {checkpoints.length === 0 && (
          <p className="sx-muted sx-pad">
            아직 단계가 없습니다. Submit을 누르면 그래프가 돌면서 여기에 쌓입니다.
          </p>
        )}

        {checkpoints.map((step) => {
          const id = step.checkpoint_id ?? "";
          return (
            <StepCard
              key={id || `${step.step}`}
              step={step}
              changed={changedKeys(step, parents.get(step.parent_checkpoint_id ?? ""))}
              lane={lanes.get(id) ?? 0}
              selected={id === selected}
              granularity={granularity}
              format={format}
              busy={busy}
              interrupted={interrupted}
              onSelect={() => id && onSelectStep(id)}
              onFork={(values) => id && onFork(id, values)}
              onRerun={() => id && onRerun(id)}
              loadFull={loadFull}
            />
          );
        })}
      </div>
    </section>
  );
}
