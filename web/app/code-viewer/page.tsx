"use client";

import DFGCodeAnnotator from "@/src/components/DFGViewer";
import { type IDFGGraph } from "@ssat/core/types/dfg";
import { useState } from "react";

export default function CodeViewerPage() {
  const [code, setCode] = useState<string>("");
  const [graph, setGraph] = useState<IDFGGraph>({ nodes: [], edges: [] });

  return (
    <div style={{ margin: "40px auto", padding: 16 }}>
      <h1 style={{ marginBottom: 8 }}>Code Viewer</h1>
      <p style={{ color: "#666", marginBottom: 24 }}>Enter a C source code and DFG to view the code with the DFG edges annotated</p>
      <textarea
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="Enter your C source code here"
        rows={10}
        style={{ width: "100%", fontFamily: "monospace" }}
      />
      <textarea
        value={JSON.stringify(graph, null, 2)}
        onChange={(e) => setGraph(JSON.parse(e.target.value) as IDFGGraph)}
        placeholder="Enter your DFG JSON here"
        rows={10}
        style={{ width: "100%", fontFamily: "monospace" }}
      />
      <DFGCodeAnnotator
        code={code}
        graph={graph}
        theme="light" // or "dark"
        height={720}
        emphasizeLines={[35, 36]}
      />
    </div>
  );
}
