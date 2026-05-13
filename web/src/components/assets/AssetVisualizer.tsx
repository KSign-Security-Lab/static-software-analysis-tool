"use client";

import React, { useState, useMemo, useCallback } from "react";
import BaseGraphVisualizer, { BaseNode, BaseLink } from "../common/BaseGraphVisualizer";
import styles from "./AssetVisualizer.module.css";

interface ViewNode {
  node_ref: string;
  node_type: string;
  label: string;
  [key: string]: unknown;
}

interface ViewEdge {
  from_ref: string;
  to_ref: string;
  edge_type: string;
  label: string;
  [key: string]: unknown;
}

interface ViewContext {
  view_context_id: string;
  asset: { name: string; asset_type?: string };
  function: { function_name: string };
  analysis_status: string;
  limitations: string[];
  lifecycle_view: { nodes: ViewNode[]; edges: ViewEdge[] };
  cleanup_path_view: { nodes: ViewNode[]; edges: ViewEdge[] };
}

interface AssetVisualizerProps {
  data: { view_contexts: ViewContext[] };
  onNodeClick: (node: BaseNode | null) => void;
  onLinkClick: (link: BaseLink | null) => void;
}

export default function AssetVisualizer({ data, onNodeClick, onLinkClick }: AssetVisualizerProps) {
  const contexts = useMemo(() => data.view_contexts || [], [data.view_contexts]);
  
  const [selectedContextId, setSelectedContextId] = useState<string | null>(
    contexts[0]?.view_context_id || null
  );

  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => {
    const allFuncs = Array.from(new Set(contexts.map(c => c.function.function_name)));
    return new Set(allFuncs.slice(1));
  });

  const selectedContext = useMemo(() => 
    contexts.find((c) => c.view_context_id === selectedContextId),
    [contexts, selectedContextId]
  );

  const groupedContexts = useMemo(() => {
    const groups: Record<string, ViewContext[]> = {};
    contexts.forEach(c => {
      const funcName = c.function.function_name;
      if (!groups[funcName]) groups[funcName] = [];
      groups[funcName].push(c);
    });
    return groups;
  }, [contexts]);

  const toggleGroup = (groupName: string) => {
    const next = new Set(collapsedGroups);
    if (next.has(groupName)) next.delete(groupName);
    else next.add(groupName);
    setCollapsedGroups(next);
  };

  const { nodes, links, cleanupBounds } = useMemo(() => {
    if (!selectedContext) return { nodes: [], links: [], cleanupBounds: null };

    const lifecycle = selectedContext.lifecycle_view || { nodes: [], edges: [] };
    const cleanup = selectedContext.cleanup_path_view || { nodes: [], edges: [] };

    const allNodesMap = new Map<string, ViewNode>();
    lifecycle.nodes.forEach(n => allNodesMap.set(n.node_ref, n));
    cleanup.nodes.forEach(n => allNodesMap.set(n.node_ref, n));

    const parsedNodes: BaseNode[] = Array.from(allNodesMap.values()).map((n) => ({
      ...n,
      id: n.node_ref,
      label: n.label || n.node_ref,
      x: 0,
      y: 0,
    }));

    const nodeMap = new Map(parsedNodes.map(n => [n.id, n]));
    const allEdges = [...lifecycle.edges, ...cleanup.edges];
    const seenEdges = new Set();
    const parsedLinks: BaseLink[] = [];

    allEdges.forEach(e => {
      const key = `${e.from_ref}-${e.to_ref}-${e.edge_type}`;
      if (!seenEdges.has(key)) {
        seenEdges.add(key);
        const source = nodeMap.get(e.from_ref);
        const target = nodeMap.get(e.to_ref);
        if (source && target) {
          parsedLinks.push({ ...e, source, target, label: e.label || e.edge_type });
        }
      }
    });

    const assetNode = parsedNodes.find(n => n.node_type === 'asset');
    const events = parsedNodes.filter(n => n.node_type === 'event' || n.node_type === 'lifecycle_event');
    const cleanupNodes = parsedNodes.filter(n => ['cleanup_jump', 'cleanup_label', 'cleanup_action'].includes(n.node_type as string));

    if (assetNode) { assetNode.x = 600; assetNode.y = 80; }

    const incomingNext = new Set(parsedLinks.filter(l => l.edge_type === 'lifecycle_order').map(l => l.target.id));
    let current: BaseNode | undefined = events.find(n => !incomingNext.has(n.id));
    const visited = new Set();
    let eventX = 150;
    while (current && !visited.has(current.id)) {
      visited.add(current.id);
      current.x = eventX;
      current.y = 350;
      eventX += 280;
      const nextLink = parsedLinks.find(l => l.edge_type === 'lifecycle_order' && l.source.id === current?.id);
      current = nextLink ? nextLink.target : undefined;
    }
    events.forEach(n => { if (!visited.has(n.id)) { n.x = eventX; n.y = 350; eventX += 280; } });

    let bounds = null;
    if (cleanupNodes.length > 0) {
      const startX = 100, startY = 550;
      let maxY = startY;
      const jumps = cleanupNodes.filter(n => n.node_type === 'cleanup_jump');
      const labels = cleanupNodes.filter(n => n.node_type === 'cleanup_label');
      const actions = cleanupNodes.filter(n => n.node_type === 'cleanup_action');
      jumps.forEach((n, i) => { n.x = startX + 150; n.y = startY + 120 + i * 130; maxY = Math.max(maxY, n.y + 100); });
      labels.forEach((n, i) => { n.x = startX + 550; n.y = startY + 120 + i * 100; maxY = Math.max(maxY, n.y + 100); });
      actions.forEach((n, i) => { n.x = startX + 950; n.y = startY + 120 + i * 120; maxY = Math.max(maxY, n.y + 100); });
      bounds = { x: startX, y: startY, w: 1100, h: maxY - startY + 50 };
    }

    return { nodes: parsedNodes, links: parsedLinks, cleanupBounds: bounds };
  }, [selectedContext]);

  const renderNode = useCallback((ctx: CanvasRenderingContext2D, node: BaseNode, isHovered: boolean, isSelected: boolean, k: number) => {
    const nodeType = node.node_type as string;
    const isAsset = nodeType === 'asset';
    const isAction = nodeType === 'cleanup_action';
    const isJump = nodeType === 'cleanup_jump';
    const isLabel = nodeType === 'cleanup_label';

    ctx.font = `bold ${14}px Inter, sans-serif`;
    const lines = node.label.split('\n');
    const textWidth = Math.max(...lines.map(l => ctx.measureText(l).width));
    const lineHeight = 18, padding = 15;
    const boxW = Math.max(textWidth + padding * 2, 140);
    const boxH = lines.length * lineHeight + padding * 2;
    node._boxW = boxW; node._boxH = boxH;

    const rx = node.x - boxW / 2, ry = node.y - boxH / 2;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(rx, ry, boxW, boxH, isAsset ? 16 : 8);
    else ctx.rect(rx, ry, boxW, boxH);

    let bgColor = "#ffffff", strokeColor = "#e2e8f0";
    if (isAsset) { bgColor = "#eff6ff"; strokeColor = "#3b82f6"; }
    else if (isJump) { bgColor = "#fff7ed"; strokeColor = "#f97316"; }
    else if (isAction) { bgColor = "#f0fdf4"; strokeColor = "#22c55e"; }
    else if (isLabel) { bgColor = "#fafafa"; strokeColor = "#71717a"; }

    if (isSelected) { strokeColor = "#2563eb"; ctx.lineWidth = 3 / k; }
    else if (isHovered) { ctx.lineWidth = 2 / k; }
    else ctx.lineWidth = 1 / k;

    ctx.fillStyle = bgColor; ctx.fill(); ctx.strokeStyle = strokeColor; ctx.stroke();
    ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillStyle = "#1e293b";
    lines.forEach((line, i) => ctx.fillText(line, node.x, ry + padding + i * lineHeight + lineHeight / 2));
    ctx.font = `9px Inter`; ctx.fillStyle = "#64748b";
    ctx.fillText(nodeType.toUpperCase().replace(/_/g, ' '), node.x, ry - 12);
  }, []);

  const renderLink = useCallback((ctx: CanvasRenderingContext2D, link: BaseLink, isHovered: boolean, isSelected: boolean, k: number) => {
    ctx.beginPath(); ctx.lineWidth = (isHovered || isSelected ? 4 : 2) / k;
    const isLifecycleOrder = link.edge_type === 'lifecycle_order';
    const isTarget = link.edge_type === 'asset_relationship' || link.edge_type === 'targets' || link.edge_type === 'cleanup_action';
    
    if (isSelected) ctx.strokeStyle = "#2563eb";
    else if (isHovered) ctx.strokeStyle = "#60a5fa";
    else if (isLifecycleOrder) ctx.strokeStyle = "#94a3b8";
    else if (isTarget) ctx.strokeStyle = "#3b82f6";
    else ctx.strokeStyle = "#cbd5e1";

    if (isLifecycleOrder) ctx.setLineDash([6, 4]);
    else ctx.setLineDash([]);

    const dx = link.target.x - link.source.x, dy = link.target.y - link.source.y;
    const angle = Math.atan2(dy, dx);
    const targetW = (link.target._boxW || 140) / 2, targetH = (link.target._boxH || 50) / 2;
    const intersectDist = Math.min(targetW / Math.abs(Math.cos(angle)), targetH / Math.abs(Math.sin(angle)));
    const tx = link.target.x - Math.cos(angle) * intersectDist, ty = link.target.y - Math.sin(angle) * intersectDist;

    ctx.moveTo(link.source.x, link.source.y); ctx.lineTo(tx, ty); ctx.stroke(); ctx.setLineDash([]); 
    const headLen = 12 / k;
    ctx.beginPath(); ctx.moveTo(tx, ty);
    ctx.lineTo(tx - headLen * Math.cos(angle - Math.PI / 6), ty - headLen * Math.sin(angle - Math.PI / 6));
    ctx.lineTo(tx - headLen * Math.cos(angle + Math.PI / 6), ty - headLen * Math.sin(angle + Math.PI / 6));
    ctx.closePath(); ctx.fillStyle = ctx.strokeStyle; ctx.fill();

    if (link.label && k > 0.4) {
      ctx.font = `${isHovered || isSelected ? 'bold ' : ''}12px Inter`;
      ctx.fillStyle = isSelected ? "#1e40af" : "#475569"; ctx.textAlign = "center";
      ctx.fillText(link.label as string, (link.source.x + tx) / 2, (link.source.y + ty) / 2 - 12);
    }
  }, []);

  const renderBackground = useCallback((ctx: CanvasRenderingContext2D) => {
    if (cleanupBounds) {
      ctx.beginPath(); ctx.lineWidth = 2; ctx.strokeStyle = "#cbd5e1"; ctx.setLineDash([12, 6]);
      if (ctx.roundRect) ctx.roundRect(cleanupBounds.x, cleanupBounds.y, cleanupBounds.w, cleanupBounds.h, 24);
      else ctx.rect(cleanupBounds.x, cleanupBounds.y, cleanupBounds.w, cleanupBounds.h);
      ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "rgba(148, 163, 184, 0.05)"; ctx.fill();
      ctx.font = "bold 18px Inter"; ctx.fillStyle = "#64748b"; ctx.textAlign = "left";
      ctx.fillText(`Relevant cleanup paths`, cleanupBounds.x + 30, cleanupBounds.y + 45);
    }
  }, [cleanupBounds]);

  return (
    <div className={styles.container}>
      <aside className={styles.leftSidebar}>
        <h2 className={styles.sidebarTitle}>Functions & Assets</h2>
        <div className={styles.contextList}>
          {Object.entries(groupedContexts).map(([funcName, items]) => {
            const isCollapsed = collapsedGroups.has(funcName);
            return (
              <div key={funcName} className={styles.group}>
                <button 
                  className={styles.groupHeader} 
                  onClick={() => toggleGroup(funcName)}
                >
                  <svg 
                    className={`${styles.chevron} ${isCollapsed ? styles.collapsed : ""}`} 
                    width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
                  >
                    <path d="M6 9l6 6 6-6" />
                  </svg>
                  {funcName}
                  <span className={styles.badge}>{items.length}</span>
                </button>
                
                {!isCollapsed && (
                  <div className={styles.groupItems}>
                    {items.map(c => (
                      <button
                        key={c.view_context_id}
                        className={`${styles.contextItem} ${selectedContextId === c.view_context_id ? styles.active : ""}`}
                        onClick={() => setSelectedContextId(c.view_context_id)}
                      >
                        <div className={styles.contextName}>{c.asset.name}</div>
                        <div className={`${styles.contextStatus} ${styles[c.analysis_status]}`}>
                          {c.analysis_status.replace(/_/g, ' ')}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </aside>

      <main className={styles.mainContent}>
        {selectedContext && (
          <section className={styles.topDetailsPanel}>
            <div className={styles.detailsRow}>
              <div className={styles.detailGroup}>
                <span className={styles.detailLabel}>Asset Name</span>
                <span className={styles.detailValueBold}>{selectedContext.asset.name}</span>
              </div>
              <div className={styles.detailGroup}>
                <span className={styles.detailLabel}>Function</span>
                <span className={styles.detailValueMono}>{selectedContext.function.function_name}</span>
              </div>
              <div className={styles.detailGroup}>
                <span className={styles.detailLabel}>Security Status</span>
                <span className={`${styles.statusBadge} ${styles[selectedContext.analysis_status]}`}>
                  {selectedContext.analysis_status.replace(/_/g, ' ')}
                </span>
              </div>
            </div>
            {selectedContext.limitations && selectedContext.limitations.length > 0 && (
              <div className={styles.limitationsRow}>
                <span className={styles.limitationsLabel}>Limitations:</span>
                <span className={styles.limitationsText}>
                  {selectedContext.limitations.join("; ")}
                </span>
              </div>
            )}
          </section>
        )}

        <div className={styles.visualizerWrapper}>
          <BaseGraphVisualizer
            nodes={nodes}
            links={links}
            onNodeClick={onNodeClick}
            onLinkClick={onLinkClick}
            renderNode={renderNode}
            renderLink={renderLink}
            renderBackground={renderBackground}
          />
        </div>
      </main>
    </div>
  );
}
