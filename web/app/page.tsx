"use client";

import { useState, useEffect } from "react";

type PipelineStage = {
  id: string;
  name: string;
  description: string;
  requires: string[];
  inputs: string[];
  outputs: string[];
  apiEndpoint: string;
};

type PipelineData = {
  stages: PipelineStage[];
  dependencies: Record<string, string[]>;
  serverRequirements: Record<string, { name: string; port: number; description: string }>;
};

export default function Home() {
  const [pipelineData, setPipelineData] = useState<PipelineData | null>(null);
  const [selectedStage, setSelectedStage] = useState<string>("cpg");
  const [inputType, setInputType] = useState<"c-source" | "cpg-data" | "template-data">("c-source");
  const [code, setCode] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [cpgData, setCpgData] = useState<string>("");
  const [templateData, setTemplateData] = useState<string>("");
  const [response, setResponse] = useState<string>("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Load pipeline options
    fetch("/api/pipeline")
      .then((res) => res.json())
      .then((data) => setPipelineData(data.data))
      .catch((err) => console.error("Failed to load pipeline options:", err));
  }, []);

  const getAvailableStages = () => {
    if (!pipelineData) return [];
    return pipelineData.stages.filter((stage) => {
      if (inputType === "c-source") return true;
      if (inputType === "cpg-data") return stage.inputs.includes("cpg-data");
      if (inputType === "template-data") return stage.inputs.includes("template-data");
      return false;
    });
  };

  const getAvailableInputTypes = (stageId: string) => {
    if (!pipelineData) return [];
    const stage = pipelineData.stages.find((s) => s.id === stageId);
    return stage?.inputs || [];
  };

  const handleStageChange = (stageId: string) => {
    setSelectedStage(stageId);
    const availableInputs = getAvailableInputTypes(stageId);
    if (availableInputs.includes("c-source")) {
      setInputType("c-source");
    } else if (availableInputs.includes("cpg-data")) {
      setInputType("cpg-data");
    } else if (availableInputs.includes("template-data")) {
      setInputType("template-data");
    }
  };

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setResponse("");

    try {
      const form = new FormData();

      if (inputType === "c-source") {
        if (file) form.set("file", file);
        if (code.trim()) form.set("code", code);
      } else if (inputType === "cpg-data") {
        if (cpgData.trim()) form.set("cpgData", cpgData);
      } else if (inputType === "template-data") {
        if (templateData.trim()) form.set("templateData", templateData);
      }

      const stage = pipelineData?.stages.find((s) => s.id === selectedStage);
      if (!stage) throw new Error("Invalid stage selected");

      const res = await fetch(stage.apiEndpoint, {
        method: "POST",
        body: form,
      });
      const data = await res.json();
      setResponse(JSON.stringify(data, null, 2));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setResponse(`Request failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  }

  if (!pipelineData) {
    return (
      <div style={{ maxWidth: 900, margin: "40px auto", padding: 16 }}>
        <h1>Loading Pipeline Options...</h1>
      </div>
    );
  }

  const availableStages = getAvailableStages();

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: 16 }}>
      <h1 style={{ marginBottom: 8 }}>C AST Generator Pipeline</h1>
      <p style={{ color: "#666", marginBottom: 24 }}>
        Choose your input type and pipeline stage. The system will guide you through the available options based on your input.
      </p>

      <form onSubmit={handleSubmit} style={{ display: "grid", gap: 16 }}>
        <div>
          <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>Input Type</label>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input type="radio" name="inputType" value="c-source" checked={inputType === "c-source"} onChange={() => setInputType("c-source")} />C
              Source Code
            </label>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input type="radio" name="inputType" value="cpg-data" checked={inputType === "cpg-data"} onChange={() => setInputType("cpg-data")} />
              CPG Data
            </label>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                type="radio"
                name="inputType"
                value="template-data"
                checked={inputType === "template-data"}
                onChange={() => setInputType("template-data")}
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

        {inputType === "c-source" && (
          <>
            <div>
              <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>Paste C code</label>
              <textarea
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="int main(){ return 0; }"
                rows={10}
                style={{ width: "100%", fontFamily: "monospace" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>Or upload a .c file</label>
              <input type="file" accept=".c,.h,.cpp,.hpp,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </div>
          </>
        )}

        {inputType === "cpg-data" && (
          <div>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>CPG Data (JSON)</label>
            <textarea
              value={cpgData}
              onChange={(e) => setCpgData(e.target.value)}
              placeholder="Paste your CPG JSON data here..."
              rows={10}
              style={{ width: "100%", fontFamily: "monospace" }}
            />
          </div>
        )}

        {inputType === "template-data" && (
          <div>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>Template Data (JSON)</label>
            <textarea
              value={templateData}
              onChange={(e) => setTemplateData(e.target.value)}
              placeholder="Paste your template JSON data here..."
              rows={10}
              style={{ width: "100%", fontFamily: "monospace" }}
            />
          </div>
        )}

        <div>
          <button type="submit" disabled={loading || availableStages.length === 0} style={{ padding: "8px 16px", fontWeight: 600 }}>
            {loading ? "Processing..." : "Process"}
          </button>
        </div>
      </form>

      <div style={{ marginTop: 24 }}>
        <label style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>API Response</label>
        <pre
          style={{
            background: "#111",
            color: "#eee",
            padding: 16,
            borderRadius: 8,
            overflowX: "auto",
          }}
        >
          {response || "(submit to see response)"}
        </pre>
      </div>
    </div>
  );
}
