"use client";

import { useQuery } from "@tanstack/react-query";
import { parseAsString, useQueryState } from "nuqs";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { describeError } from "@/lib/api/client";
import { analyze, f2aFromCpg } from "@/lib/api/ssat";
import { looksLikeCpg, unwrapCpgDocument } from "@/lib/cpg";
import { keys } from "@/lib/query/keys";
import { SAMPLES } from "@/lib/samples";
import type { AnalyzeResponse } from "@/lib/types";

interface CpgSource {
  sampleId: string;
  sample: (typeof SAMPLES)[number];
  text: string;
  name: string;
  language: string;
  analyzed: string | null;
  response: AnalyzeResponse | null;
  analyzing: boolean;
  opening: boolean;
  setText: (value: string) => void;
  pick: (id: string) => void;
  analyse: () => void;
  open: (file: File) => void;
}

const Context = createContext<CpgSource | null>(null);

function hash(value: string): number {
  let out = 0;
  for (let i = 0; i < value.length; i += 1) out = (Math.imul(31, out) + value.charCodeAt(i)) | 0;
  return out;
}

export function CpgSourceProvider({ children }: { children: ReactNode }) {
  const [sampleId, setSampleId] = useQueryState(
    "sample",
    parseAsString.withDefault(SAMPLES[0].id).withOptions({ history: "replace" }),
  );
  const sample = useMemo(() => SAMPLES.find((each) => each.id === sampleId) ?? SAMPLES[0], [sampleId]);

  const [draft, setDraft] = useState<string | null>(null);
  const [opened, setOpened] = useState<{ name: string; language?: string } | null>(null);
  const [opening, setOpening] = useState(false);

  const text = draft ?? sample.source;
  const name = opened?.name ?? sample.filename;
  const language = opened?.language ?? sample.language;

  const cacheKey = `${language}:${name}:${hash(text)}`;

  const query = useQuery({
    queryKey: keys.analyze(cacheKey),
    queryFn: async () => ({ result: await analyze({ source: text, language, filename: name }), analyzed: text }),
    enabled: false,
    staleTime: Infinity,
    gcTime: 30 * 60 * 1000,
  });

  const analyse = useCallback(() => {
    void query.refetch().then((result) => {
      if (result.error) toast.error("분석 실패", { description: describeError(result.error) });
    });
  }, [query]);

  const open = useCallback((file: File) => {
    setOpening(true);
    void (async () => {
      try {
        const content = await file.text();
        if (file.name.toLowerCase().endsWith(".json")) {
          const raw: unknown = JSON.parse(content);
          if (!looksLikeCpg(raw)) throw new Error("CPG JSON이 아닙니다 (vertices/edges를 찾을 수 없습니다).");
          await f2aFromCpg(unwrapCpgDocument(raw));
          toast.info("CPG JSON을 열었습니다. ‘분석’은 소스에만 적용됩니다.");
          setOpened({ name: file.name });
          return;
        }
        setOpened({ name: file.name });
        setDraft(content);
      } catch (error) {
        toast.error("열 수 없습니다", { description: describeError(error) });
      } finally {
        setOpening(false);
      }
    })();
  }, []);

  const pick = useCallback(
    (id: string) => {
      void setSampleId(id);
      setDraft(null);
      setOpened(null);
    },
    [setSampleId],
  );

  const value = useMemo<CpgSource>(
    () => ({
      sampleId: sample.id,
      sample,
      text,
      name,
      language,
      analyzed: query.data?.analyzed ?? null,
      response: query.data?.result ?? null,
      analyzing: query.isFetching,
      opening,
      setText: setDraft,
      pick,
      analyse,
      open,
    }),
    [sample, text, name, language, query.data, query.isFetching, opening, pick, analyse, open],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useCpgSource(): CpgSource {
  const source = useContext(Context);
  if (!source) throw new Error("useCpgSource must be used inside <CpgSourceProvider>");
  return source;
}
