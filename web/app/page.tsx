"use client";

import React, { useState } from "react";
import Link from "next/link";
import { CPGUploader } from "@/src/components/cpg/CPGUploader";
import GraphVisualizer from "@/src/components/cpg/GraphVisualizer";
import { NodePropertiesPanel } from "@/src/components/cpg/NodePropertiesPanel";
import styles from "./page.module.css";

export default function CPGViewerPage() {
  const [graphData, setGraphData] = useState<any | null>(null);
  const [selectedNode, setSelectedNode] = useState<any | null>(null);

  const handleUpload = (data: any) => {
    setGraphData(data);
    setSelectedNode(null);
  }

  const handleReset = () => {
    setGraphData(null);
    setSelectedNode(null);
  }

  return (
    <div className={styles.pageContainer}>
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <Link href="/generate" className={styles.backButton} style={{ padding: "0.5rem 1rem", borderRadius: "8px", fontSize: "0.875rem", fontWeight: 500, backgroundColor: "rgba(59, 130, 246, 0.1)", color: "#3b82f6" }}>
            Generator
          </Link>
          <h1 className={styles.title}>CPG Viewer</h1>
        </div>
        {graphData && (
          <button onClick={handleReset} className={styles.resetButton}>
            Upload New Graph
          </button>
        )}
      </header>

      <main className={styles.mainContent}>
        {!graphData ? (
          <div className={styles.uploadSection}>
            <div className={styles.heroText}>
              <h2 className={styles.heroTitle}>Visualize your Code Property Graph</h2>
              <p className={styles.heroDescription}>
                Upload a JSON file representing your CPG to dynamically explore nodes and edges.
                Useful for debugging AST, CFG, and PDG structures in a fully interactive visualizer.
              </p>
            </div>
            <CPGUploader onUpload={handleUpload} />
          </div>
        ) : (
          <div className={styles.visualizerWrapper}>
            <GraphVisualizer data={graphData} onNodeClick={setSelectedNode} />
            {selectedNode && (
              <NodePropertiesPanel node={selectedNode} onClose={() => setSelectedNode(null)} />
            )}
          </div>
        )}
      </main>
    </div>
  );
}
