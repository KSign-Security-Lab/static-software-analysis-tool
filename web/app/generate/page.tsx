"use client";

import { useReducer } from "react";
import type { PipelineData, PipelineStage } from "@/src/pipeline/types";
import { InputType } from "@/src/pipeline/types";
import { defaultStageForInput, filterStagesForInput, findStage } from "@/src/pipeline/helpers";
import { pipelineOptions } from "@/src/pipeline/config";

type State = {
  pipeline: PipelineData;
  inputType: InputType;
  selectedStage: string | null;
  code: string;
  file: File | null;
  cpgData: string;
  templateData: string;
  response: string;
  loading: boolean;
};

type Action =
  | { type: "setInputType"; payload: InputType }
  | { type: "setStage"; payload: string }
  | { type: "setCode"; payload: string }
  | { type: "setFile"; payload: File | null }
  | { type: "setCPG"; payload: string }
  | { type: "setTemplate"; payload: string }
  | { type: "setResponse"; payload: string }
  | { type: "setLoading"; payload: boolean };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "setInputType": {
      // Keep current stage if still valid for the new input; otherwise pick the first valid stage
      const available = filterStagesForInput(state.pipeline, action.payload);
      const keepCurrent = available.find((s) => s.id === state.selectedStage)?.id ?? null;
      const nextStage = keepCurrent ?? available[0]?.id ?? null;
      return { ...state, inputType: action.payload, selectedStage: nextStage };
    }
    case "setStage":
      return { ...state, selectedStage: action.payload };
    case "setCode":
      return { ...state, code: action.payload };
    case "setFile":
      return { ...state, file: action.payload };
    case "setCPG":
      return { ...state, cpgData: action.payload };
    case "setTemplate":
      return { ...state, templateData: action.payload };
    case "setResponse":
      return { ...state, response: action.payload };
    case "setLoading":
      return { ...state, loading: action.payload };
    default:
      return state;
  }
}

export default function Home() {
  const [state, dispatch] = useReducer(reducer, {
    pipeline: pipelineOptions,
    inputType: InputType.CSource,
    selectedStage: defaultStageForInput(pipelineOptions, InputType.CSource) ?? null,
    code: "",
    file: null,
    cpgData: "",
    templateData: "",
    response: "",
    loading: false,
  });

  const getAvailableStages = () => {
    return filterStagesForInput(state.pipeline, state.inputType);
  };

  const handleStageChange = (stageId: string) => {
    const stage = findStage(state.pipeline, stageId);
    if (!stage) return;
    dispatch({ type: "setStage", payload: stageId });
    if (!stage.inputs.includes(state.inputType)) {
      // Prefer keeping user's current non c-source intent when possible
      const preferred = stage.inputs.includes(state.inputType)
        ? state.inputType
        : (stage.inputs.find((i) => i !== InputType.CSource) ?? stage.inputs[0]);
      dispatch({ type: "setInputType", payload: preferred });
    }
  };

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    dispatch({ type: "setLoading", payload: true });
    dispatch({ type: "setResponse", payload: "" });

    try {
      const form = new FormData();

      if (state.inputType === InputType.CSource) {
        if (state.file) form.set("file", state.file);
        if (state.code.trim()) form.set("code", state.code);
      } else if (state.inputType === InputType.CpgData) {
        if (state.cpgData.trim()) form.set("cpgData", state.cpgData);
      } else if (state.inputType === InputType.TemplateData) {
        if (state.templateData.trim()) form.set("templateData", state.templateData);
      }

      const stage = state.pipeline.stages.find((s) => s.id === state.selectedStage);
      if (!stage) throw new Error("Invalid stage selected");

      const res = await fetch(stage.apiEndpoint, {
        method: "POST",
        body: form,
      });
      const data = await res.json();
      dispatch({ type: "setResponse", payload: JSON.stringify(data, null, 2) });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      dispatch({ type: "setResponse", payload: `Request failed: ${msg}` });
    } finally {
      dispatch({ type: "setLoading", payload: false });
    }
  }

  const copyResponse = async () => {
    try {
      await navigator.clipboard.writeText(state.response || "");
    } catch (e) {
      console.error("Copy failed", e);
    }
  };

  const availableStages = getAvailableStages();
  const selectedStage = availableStages.find((s) => s.id === state.selectedStage)?.id ?? availableStages[0]?.id ?? "";

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: 16 }}>
      <h1 style={{ marginBottom: 8 }}>C AST Generator Pipeline</h1>
      <p style={{ color: "#666", marginBottom: 24 }}>
        Choose your input type and pipeline stage. The system will guide you through the available options based on your input.
      </p>

      {state.pipeline && (
        <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 16, marginBottom: 24 }}>
          <div style={{ fontWeight: 700, marginBottom: 12 }}>Pipeline Overview</div>
          <div style={{ display: "grid", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <Tag label="C Source" color="#eef6ff" />
              <span>→</span>
              <StageTag id="cpg" stages={state.pipeline.stages} selected={selectedStage} onSelect={handleStageChange} />
              <span>→</span>
              <StageTag id="template" stages={state.pipeline.stages} selected={selectedStage} onSelect={handleStageChange} />
              <span>→</span>
              <StageTag id="ast" stages={state.pipeline.stages} selected={selectedStage} onSelect={handleStageChange} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <Tag label="CPG Data" color="#f5fff0" />
              <span>→</span>
              <StageTag id="dfg" stages={state.pipeline.stages} selected={selectedStage} onSelect={handleStageChange} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <Tag label="Template Data" color="#fff4ef" />
              <span>→</span>
              <StageTag id="ast" stages={state.pipeline.stages} selected={selectedStage} onSelect={handleStageChange} />
            </div>
            <div style={{ fontSize: 12, color: "#888", marginTop: 8 }}>
              Joern server on port {state.pipeline.serverRequirements["joern-server"].port} for CPG; AST server on port{" "}
              {state.pipeline.serverRequirements["ast-server"].port} for AST.
            </div>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display: "grid", gap: 16 }}>
        <div>
          <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>Input Type</label>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                type="radio"
                name="inputType"
                value={InputType.CSource}
                checked={state.inputType === InputType.CSource}
                onChange={() => dispatch({ type: "setInputType", payload: InputType.CSource })}
              />
              C Source Code
            </label>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                type="radio"
                name="inputType"
                value={InputType.CpgData}
                checked={state.inputType === InputType.CpgData}
                onChange={() => dispatch({ type: "setInputType", payload: InputType.CpgData })}
              />
              CPG Data
            </label>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                type="radio"
                name="inputType"
                value={InputType.TemplateData}
                checked={state.inputType === InputType.TemplateData}
                onChange={() => dispatch({ type: "setInputType", payload: InputType.TemplateData })}
              />
              Template Data
            </label>
          </div>
        </div>

        <div>
          <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>Pipeline Stage</label>
          <div style={{ display: "grid", gap: 8 }}>
            {availableStages.map((stage) => (
              <label
                key={stage.id}
                style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: 12, border: "1px solid #ddd", borderRadius: 8 }}
              >
                <input type="radio" name="stage" value={stage.id} checked={selectedStage === stage.id} onChange={() => handleStageChange(stage.id)} />
                <div>
                  <div style={{ fontWeight: 600 }}>{stage.name}</div>
                  <div style={{ fontSize: 14, color: "#666" }}>{stage.description}</div>
                  <div style={{ fontSize: 12, color: "#888", marginTop: 4 }}>
                    Requires: {stage.requires.join(", ")} | Outputs: {stage.outputs.join(", ")}
                  </div>
                </div>
              </label>
            ))}
          </div>
        </div>

        {state.inputType === InputType.CSource && (
          <>
            <div>
              <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>Paste C code</label>
              <textarea
                value={state.code}
                onChange={(e) => dispatch({ type: "setCode", payload: e.target.value })}
                placeholder="int main(){ return 0; }"
                rows={10}
                style={{ width: "100%", fontFamily: "monospace" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>Or upload a .c file</label>
              <input
                type="file"
                accept=".c,.h,.cpp,.hpp,.txt"
                onChange={(e) => dispatch({ type: "setFile", payload: e.target.files?.[0] ?? null })}
              />
            </div>
          </>
        )}

        {state.inputType === InputType.CpgData && (
          <div>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>CPG Data (JSON file only)</label>
            <input
              type="file"
              accept=".json,application/json"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) {
                  dispatch({ type: "setCPG", payload: "" });
                  return;
                }
                try {
                  const text = await f.text();
                  dispatch({ type: "setCPG", payload: text });
                } catch {
                  dispatch({ type: "setCPG", payload: "" });
                }
              }}
            />
            <textarea
              value={state.cpgData}
              readOnly
              disabled
              placeholder="Upload a JSON file to load CPG data"
              rows={10}
              style={{ width: "100%", fontFamily: "monospace", marginTop: 8, opacity: 0.7 }}
            />
          </div>
        )}

        {state.inputType === InputType.TemplateData && (
          <div>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>Template Data (JSON file only)</label>
            <input
              type="file"
              accept=".json,application/json"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) {
                  dispatch({ type: "setTemplate", payload: "" });
                  return;
                }
                try {
                  const text = await f.text();
                  dispatch({ type: "setTemplate", payload: text });
                } catch {
                  dispatch({ type: "setTemplate", payload: "" });
                }
              }}
            />
            <textarea
              value={state.templateData}
              readOnly
              disabled
              placeholder="Upload a JSON file to load Template data"
              rows={10}
              style={{ width: "100%", fontFamily: "monospace", marginTop: 8, opacity: 0.7 }}
            />
          </div>
        )}

        <div>
          <button type="submit" disabled={state.loading || availableStages.length === 0} style={{ padding: "8px 16px", fontWeight: 600 }}>
            {state.loading ? "Processing..." : "Process"}
          </button>
        </div>
      </form>

      <div style={{ marginTop: 24 }}>
        <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>API Response</label>
        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          <button type="button" onClick={copyResponse} style={{ padding: "6px 12px", fontWeight: 600 }}>
            Copy
          </button>
        </div>
        <pre
          style={{
            background: "#111",
            color: "#eee",
            padding: 16,
            borderRadius: 8,
            overflowX: "auto",
          }}
        >
          {state.response || "(submit to see response)"}
        </pre>
      </div>
    </div>
  );
}

function Tag({ label, color = "#eee" }: { label: string; color?: string }) {
  return (
    <span
      style={{
        background: color,
        border: "1px solid #ddd",
        borderRadius: 6,
        padding: "4px 8px",
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {label}
    </span>
  );
}

function StageTag({ id, stages, selected, onSelect }: { id: string; stages: PipelineStage[]; selected: string; onSelect: (id: string) => void }) {
  const stage = stages.find((s) => s.id === id);
  if (!stage) return <Tag label={`Unknown(${id})`} />;
  const isSelected = selected === id;
  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      title={stage.description}
      style={{
        background: isSelected ? "#e8f5e9" : "#f7f7f7",
        border: isSelected ? "1px solid #66bb6a" : "1px solid #ddd",
        borderRadius: 6,
        padding: "4px 8px",
        fontSize: 12,
        fontWeight: 700,
        cursor: "pointer",
      }}
    >
      {stage.name}
    </button>
  );
}
