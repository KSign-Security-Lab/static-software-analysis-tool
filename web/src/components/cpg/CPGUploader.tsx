"use client";

import React, { useCallback, useState } from "react";
import styles from "./CPGUploader.module.css";

interface CPGUploaderProps {
  onUpload: (data: any) => void;
}

export function CPGUploader({ onUpload }: CPGUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = (file: File) => {
    setError(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const text = e.target?.result as string;
        const data = JSON.parse(text);
        
        // Basic validation for generic graph data or CPG format.
        // CPG JSON might just be an array of objects or have nodes/edges.
        // We'll normalize in the visualizer, but basic checks here.
        if (!data || typeof data !== "object") {
          throw new Error("Invalid format: JSON must be an object or array.");
        }
        
        onUpload(data);
      } catch (err: any) {
        setError(err.message || "Failed to parse JSON file.");
      }
    };
    reader.onerror = () => setError("Failed to read file.");
    reader.readAsText(file);
  };

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  }, []);

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
  };

  return (
    <div
      className={`${styles.uploaderContainer} ${isDragging ? styles.dragging : ""}`}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <div className={styles.iconWrapper}>
        <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
        </svg>
      </div>
      <h3 className={styles.title}>Upload CPG JSON</h3>
      <p className={styles.description}>
        Drag and drop your Code Property Graph JSON file here, or click to browse.
      </p>
      <label className={styles.browseButton}>
        Browse File
        <input
          type="file"
          className={styles.hiddenInput}
          accept=".json,application/json"
          onChange={onChange}
        />
      </label>
      {error && (
        <div className={styles.error}>
          {error}
        </div>
      )}
    </div>
  );
}
