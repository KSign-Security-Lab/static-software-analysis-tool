"use client";

import { useCallback, useRef, useState } from "react";

import { analyze, f2aFromCpg } from "@/lib/api/ssat";
import { looksLikeCpg, unwrapCpgDocument } from "@/lib/cpg";
import { SAMPLES } from "@/lib/samples";
import type { AnalyzeResponse } from "@/lib/types";

/**
 * Getting a CPG, shared by the two sections that need one.
 *
 * F2-A and extraction both start from "compile this source, or open this CPG
 * JSON". Duplicating that gave two subtly different upload rules; this is the
 * one implementation, returned as state plus a toolbar to drive it.
 */
export interface CpgSourceState {
  source: string;
  setSource: (value: string) => void;
  language: string;
  filename: string;
  analyzed: string;
  response: AnalyzeResponse | null;
  loading: boolean;
  error: string | null;
  run: () => Promise<void>;
  loadFile: (file: File) => Promise<void>;
  loadSample: (id: string) => void;
}

export function useCpgSource(): CpgSourceState {
  const [source, setSource] = useState(SAMPLES[0].source);
  const [language, setLanguage] = useState(SAMPLES[0].language);
  const [filename, setFilename] = useState(SAMPLES[0].filename);
  const [analyzed, setAnalyzed] = useState("");
  const [response, setResponse] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await analyze({ source, language, filename });
      setResponse(res);
      setAnalyzed(source);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResponse(null);
    } finally {
      setLoading(false);
    }
  }, [source, language, filename]);

  const loadFile = useCallback(async (file: File) => {
    setError(null);
    const text = await file.text();

    // A CPG JSON skips Joern: there is no source to compile.
    if (file.name.toLowerCase().endsWith(".json")) {
      const raw: unknown = JSON.parse(text);
      if (!looksLikeCpg(raw)) {
        setError("CPG JSON이 아닙니다 (vertices/edges를 찾을 수 없습니다).");
        return;
      }
      setLoading(true);
      try {
        const cpg = unwrapCpgDocument(raw);
        const f2a = await f2aFromCpg(cpg);
        setResponse({ cpg, method_count: 0, f2a });
        setAnalyzed("");
        setFilename(file.name);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
      return;
    }

    setSource(text);
    setFilename(file.name);
  }, []);

  const loadSample = useCallback((id: string) => {
    const sample = SAMPLES.find((s) => s.id === id);
    if (!sample) return;
    setSource(sample.source);
    setLanguage(sample.language);
    setFilename(sample.filename);
  }, []);

  return {
    source,
    setSource,
    language,
    filename,
    analyzed,
    response,
    loading,
    error,
    run,
    loadFile,
    loadSample,
  };
}

/** The controls for the above, as a compact strip. */
export function CpgSourceBar({ state, meta }: { state: CpgSourceState; meta?: string }) {
  const fileInput = useRef<HTMLInputElement>(null);

  return (
    <>
      <select className="target-select" defaultValue="" onChange={(e) => e.target.value && state.loadSample(e.target.value)}>
        <option value="">예제…</option>
        {SAMPLES.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label}
          </option>
        ))}
      </select>

      <button type="button" className="btn" onClick={() => fileInput.current?.click()}>
        열기
      </button>
      <input
        ref={fileInput}
        type="file"
        hidden
        accept=".c,.h,.cpp,.cc,.cxx,.hpp,.hxx,.java,.json"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) state.loadFile(file);
          e.target.value = "";
        }}
      />

      <button type="button" className="btn btn-primary" onClick={state.run} disabled={state.loading}>
        {state.loading ? "분석 중…" : "분석"}
      </button>

      {meta && <span className="target-stats">{meta}</span>}
      <span className="target-hint">소스 또는 CPG JSON · 편집기에서 바로 수정</span>
    </>
  );
}
