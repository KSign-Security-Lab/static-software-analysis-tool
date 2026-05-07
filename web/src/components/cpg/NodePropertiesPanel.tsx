"use client";

import React from "react";
import styles from "./NodePropertiesPanel.module.css";

interface NodePropertiesPanelProps {
  node: any;
  onClose: () => void;
}

export function NodePropertiesPanel({ node, onClose }: NodePropertiesPanelProps) {
  if (!node) return null;

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h3 className={styles.title}>
          <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Node Inspector
        </h3>
        <button onClick={onClose} className={styles.closeButton}>
          <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div className={styles.content}>
        {(() => {
          // Flatten node attributes and properties
          const flatProps: Record<string, any> = {};
          
          const extractValue = (obj: any): any => {
            if (obj && typeof obj === 'object') {
              if (obj["@value"] !== undefined) {
                let val = obj["@value"];
                if (val && typeof val === 'object' && val["@value"] !== undefined) {
                    val = val["@value"];
                }
                if (Array.isArray(val) && val.length === 1) {
                    return val[0];
                }
                return val;
              }
            }
            return obj;
          };

          // Add top-level attributes (id, label)
          if (node.id) flatProps["id"] = extractValue(node.id);
          if (node.label) flatProps["label"] = node.label;

          // Add TinkerPop properties
          if (node.properties) {
            Object.entries(node.properties).forEach(([k, v]) => {
              flatProps[k] = extractValue(v);
            });
          } else {
            // Generic fallback
            Object.entries(node).forEach(([k, v]) => {
              if (!["_id", "x", "y", "vx", "vy", "color", "properties", "id", "label"].includes(k)) {
                flatProps[k] = v;
              }
            });
          }

          return Object.entries(flatProps).map(([key, value]) => {
            let displayValue = "";
            if (typeof value === "object") {
              displayValue = JSON.stringify(value, null, 2);
            } else {
              displayValue = String(value);
            }

            return (
              <div key={key} className={styles.propertyRow}>
                <span className={styles.propertyKey}>{key}</span>
                <span className={styles.propertyValue}>{displayValue}</span>
              </div>
            );
          });
        })()}
      </div>
    </div>
  );
}
