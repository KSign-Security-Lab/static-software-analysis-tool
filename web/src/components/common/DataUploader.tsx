"use client";

import React, { useCallback, useState } from "react";
import styles from "./DataUploader.module.css";

interface DataUploaderProps {
  onUpload: (data: any, type: "cpg" | "asset") => void;
  title?: string;
  description?: string;
}

export function DataUploader({ 
  onUpload, 
  title = "Upload Data JSON", 
  description = "Drag and drop your JSON file here, or click to browse." 
}: DataUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback((file: File) => {
    setError(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const text = e.target?.result as string;
        const data = JSON.parse(text);
        
        let type: "cpg" | "asset" = "cpg";
        if (data.artifact_type === "visualization_context") {
          type = "asset";
        } else if (data["@type"] === "tinker:graph") {
          type = "cpg";
        }
        
        onUpload(data, type);
      } catch (err: any) {
        setError(err.message || "Failed to parse JSON file.");
      }
    };
    reader.onerror = () => setError("Failed to read file.");
    reader.readAsText(file);
  }, [onUpload]);

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
  }, [handleFile]);

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
      <h3 className={styles.title}>{title}</h3>
      <p className={styles.description}>
        {description}
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
