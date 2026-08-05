"use client";

import { useMemo } from "react";

import { usePrompts, useSpans } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import SpanInspector from "./SpanInspector";
import { useSelectedSpan } from "./state";

export default function TraceInspectorPane() {
  const [runId] = useRunId();
  const [spanId] = useSelectedSpan();

  const spans = useSpans(runId);
  const prompts = usePrompts();

  const span = useMemo(
    () => spans.data?.spans.find((each) => each.id === spanId) ?? null,
    [spans.data, spanId],
  );

  return <SpanInspector runId={runId} span={span} prompts={prompts.data ?? []} />;
}
