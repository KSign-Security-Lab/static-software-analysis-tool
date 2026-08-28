"use client";

import React, { useState } from "react";
import Link from "next/link";
import { DataUploader } from "@/src/components/common/DataUploader";
import AssetVisualizer from "@/src/components/assets/AssetVisualizer";
import { NodePropertiesPanel } from "@/src/components/cpg/NodePropertiesPanel";
import styles from "../page.module.css";

export default function AssetVisualizerPage() {
  const [graphData, setGraphData] = useState<any | null>(null);
  const [selectedItem, setSelectedItem] = useState<any | null>(null);

  const handleUpload = (data: any) => {
    setGraphData(data);
    setSelectedItem(null);
  };

  const handleReset = () => {
    setGraphData(null);
    setSelectedItem(null);
  };

  return (
    <div className={styles.pageContainer}>
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <Link href="/generate" className={styles.backButton} style={{ padding: "0.5rem 1rem", borderRadius: "8px", fontSize: "0.875rem", fontWeight: 500, backgroundColor: "rgba(59, 130, 246, 0.1)", color: "#3b82f6", marginRight: "1rem" }}>
            Generator
          </Link>
          <Link href="/" className={styles.backButton} style={{ padding: "0.5rem 1rem", borderRadius: "8px", fontSize: "0.875rem", fontWeight: 500, backgroundColor: "rgba(139, 92, 246, 0.1)", color: "#8b5cf6", marginRight: "1rem" }}>
            CPG Viewer
          </Link>
          <h1 className={styles.title}>Asset Lifecycle Visualizer</h1>
        </div>
        {graphData && (
          <button onClick={handleReset} className={styles.resetButton}>
            Upload New File
          </button>
        )}
      </header>

      <main className={styles.mainContent}>
        {!graphData ? (
          <div className={styles.uploadSection}>
            <div className={styles.heroText}>
              <h2 className={styles.heroTitle}>Visualize Asset Lifecycles</h2>
              <p className={styles.heroDescription}>
                Upload a Asset Visualization Context JSON (v0.6) to explore security-relevant asset paths and cleanup jumps.
              </p>
            </div>
            <DataUploader 
              onUpload={handleUpload} 
              title="Upload Asset Context" 
              description="Drag and drop your Asset Visualization Context JSON (v0.6) here." 
            />
          </div>
        ) : (
          <div className={styles.visualizerWrapper}>
            <AssetVisualizer 
              data={graphData} 
              onNodeClick={setSelectedItem} 
              onLinkClick={setSelectedItem} 
            />
            {selectedItem && (
              <NodePropertiesPanel node={selectedItem} onClose={() => setSelectedItem(null)} />
            )}
          </div>
        )}
      </main>
    </div>
  );
}
