"use client";

import React, { useEffect, useRef } from "react";
import styles from "./BaseGraphVisualizer.module.css";

export interface BaseNode {
  id: string | number;
  x: number;
  y: number;
  label: string;
  color?: string;
  _boxW?: number;
  _boxH?: number;
  _layoutW?: number;
  _layoutH?: number;
  [key: string]: unknown;
}

export interface BaseLink {
  source: BaseNode;
  target: BaseNode;
  label: string;
  edge_type?: string;
  [key: string]: unknown;
}

interface CanvasWithDraw extends HTMLCanvasElement {
  _draw?: () => void;
}

interface BaseGraphVisualizerProps {
  nodes: BaseNode[];
  links: BaseLink[];
  onNodeClick?: (node: BaseNode | null) => void;
  onLinkClick?: (link: BaseLink | null) => void;
  nodeWidth?: number;
  nodeHeight?: number;
  renderNode?: (ctx: CanvasRenderingContext2D, node: BaseNode, isHovered: boolean, isSelected: boolean, k: number) => void;
  renderLink?: (ctx: CanvasRenderingContext2D, link: BaseLink, isHovered: boolean, isSelected: boolean, k: number) => void;
  renderBackground?: (ctx: CanvasRenderingContext2D, k: number) => void;
  renderForeground?: (ctx: CanvasRenderingContext2D, k: number) => void;
}

export default function BaseGraphVisualizer({
  nodes,
  links,
  onNodeClick,
  onLinkClick,
  nodeWidth = 120,
  nodeHeight = 40,
  renderNode,
  renderLink,
  renderBackground,
  renderForeground
}: BaseGraphVisualizerProps) {
  const canvasRef = useRef<CanvasWithDraw>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  
  const transformRef = useRef({ x: 0, y: 0, k: 0.5 });
  const isDraggingRef = useRef(false);
  const lastMouseRef = useRef({ x: 0, y: 0 });
  const hoveredNodeRef = useRef<BaseNode | null>(null);
  const selectedNodeRef = useRef<BaseNode | null>(null);
  const hoveredLinkRef = useRef<BaseLink | null>(null);
  const selectedLinkRef = useRef<BaseLink | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const draw = () => {
      if (!ctx || !canvas) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.save();
      
      const { x, y, k } = transformRef.current;
      ctx.translate(x, y);
      ctx.scale(k, k);

      if (renderBackground) renderBackground(ctx, k);

      const viewMinX = -x / k;
      const viewMaxX = (canvas.width - x) / k;
      const viewMinY = -y / k;
      const viewMaxY = (canvas.height - y) / k;
      
      const isVisible = (nx: number, ny: number, pad = 150) => 
        nx >= viewMinX - pad && nx <= viewMaxX + pad && 
        ny >= viewMinY - pad && ny <= viewMaxY + pad;

      for (const link of links) {
        if (isVisible(link.source.x, link.source.y) || isVisible(link.target.x, link.target.y)) {
          const isHovered = hoveredLinkRef.current === link;
          const isSelected = selectedLinkRef.current === link;
          if (renderLink) {
            renderLink(ctx, link, isHovered, isSelected, k);
          } else {
            ctx.lineWidth = (isSelected || isHovered ? 3 : 1) / k;
            ctx.strokeStyle = isSelected ? "#3b82f6" : (isHovered ? "#60a5fa" : "rgba(100, 116, 139, 0.2)");
            ctx.beginPath();
            ctx.moveTo(link.source.x, link.source.y);
            ctx.lineTo(link.target.x, link.target.y);
            ctx.stroke();
          }
        }
      }

      for (const node of nodes) {
        if (!isVisible(node.x, node.y)) continue;
        const isHovered = hoveredNodeRef.current === node;
        const isSelected = selectedNodeRef.current === node;
        if (renderNode) {
          renderNode(ctx, node, isHovered, isSelected, k);
        } else {
          ctx.beginPath();
          ctx.arc(node.x, node.y, 5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      
      if (renderForeground) renderForeground(ctx, k);
      ctx.restore();
    };

    const resize = () => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (rect) {
        const dpr = window.devicePixelRatio || 1;
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        canvas.style.width = `${rect.width}px`;
        canvas.style.height = `${rect.height}px`;
        ctx.scale(dpr, dpr);
        draw();
      }
    };

    window.addEventListener("resize", resize);
    resize();
    
    if (nodes.length > 0) {
      const padding = 50;
      const dpr = window.devicePixelRatio || 1;
      const cw = canvas.width / dpr;
      const ch = canvas.height / dpr;
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      nodes.forEach(n => {
        minX = Math.min(minX, n.x - (n._boxW || 120) / 2);
        maxX = Math.max(maxX, n.x + (n._boxW || 120) / 2);
        minY = Math.min(minY, n.y - (n._boxH || 40) / 2);
        maxY = Math.max(maxY, n.y + (n._boxH || 40) / 2);
      });
      const graphW = maxX - minX;
      const graphH = maxY - minY;
      const scaleX = (cw - padding * 2) / (graphW || 1);
      const scaleY = (ch - padding * 2) / (graphH || 1);
      const newK = Math.max(0.1, Math.min(1.0, Math.min(scaleX, scaleY)));
      const newX = (cw - graphW * newK) / 2 - minX * newK;
      const newY = (ch - graphH * newK) / 2 - minY * newK;
      transformRef.current = { x: newX, y: newY, k: newK };
      draw();
    }

    canvas._draw = draw;
    return () => {
      window.removeEventListener("resize", resize);
      delete canvas._draw;
    };
  }, [nodes, links, renderNode, renderLink, renderBackground, renderForeground]);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const scaleFactor = e.deltaY > 0 ? 0.9 : 1.1;
    const { x, y, k } = transformRef.current;
    const rect = canvasRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const newK = Math.max(0.05, Math.min(10, k * scaleFactor));
    const newX = mx - (mx - x) * (newK / k);
    const newY = my - (my - y) * (newK / k);
    transformRef.current = { x: newX, y: newY, k: newK };
    canvasRef.current?._draw?.();
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    isDraggingRef.current = true;
    const rect = canvasRef.current!.getBoundingClientRect();
    lastMouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const pos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    const { x, y, k } = transformRef.current;
    const tx = (pos.x - x) / k;
    const ty = (pos.y - y) / k;

    if (isDraggingRef.current) {
      transformRef.current.x += pos.x - lastMouseRef.current.x;
      transformRef.current.y += pos.y - lastMouseRef.current.y;
      lastMouseRef.current = pos;
      canvasRef.current?._draw?.();
    } else {
      let foundNode: BaseNode | null = null;
      for (let i = nodes.length - 1; i >= 0; i--) {
        const node = nodes[i];
        const boxW = node._boxW || nodeWidth;
        const boxH = node._boxH || nodeHeight;
        if (tx >= node.x - boxW/2 && tx <= node.x + boxW/2 && ty >= node.y - boxH/2 && ty <= node.y + boxH/2) {
          foundNode = node;
          break;
        }
      }

      let foundLink: BaseLink | null = null;
      if (!foundNode) {
        const threshold = 10 / k;
        for (const link of links) {
          const { x: x1, y: y1 } = link.source;
          const { x: x2, y: y2 } = link.target;
          const L2 = (x2 - x1) ** 2 + (y2 - y1) ** 2;
          if (L2 === 0) continue;
          const t = Math.max(0, Math.min(1, ((tx - x1) * (x2 - x1) + (ty - y1) * (y2 - y1)) / L2));
          const distSq = (tx - (x1 + t * (x2 - x1))) ** 2 + (ty - (y1 + t * (y2 - y1))) ** 2;
          if (distSq < threshold ** 2) {
            foundLink = link;
            break;
          }
        }
      }

      if (hoveredNodeRef.current !== foundNode || hoveredLinkRef.current !== foundLink) {
        hoveredNodeRef.current = foundNode;
        hoveredLinkRef.current = foundLink;
        if (canvasRef.current) canvasRef.current.style.cursor = (foundNode || foundLink) ? "pointer" : "grab";
        canvasRef.current?._draw?.();
      }
    }
  };

  const handleMouseUp = () => { isDraggingRef.current = false; };

  const handleClick = () => {
    if (hoveredNodeRef.current) {
      selectedNodeRef.current = hoveredNodeRef.current;
      selectedLinkRef.current = null;
      if (onNodeClick) onNodeClick(hoveredNodeRef.current);
    } else if (hoveredLinkRef.current) {
      selectedLinkRef.current = hoveredLinkRef.current;
      selectedNodeRef.current = null;
      if (onLinkClick) onLinkClick(hoveredLinkRef.current);
    } else {
      selectedNodeRef.current = null;
      selectedLinkRef.current = null;
      if (onNodeClick) onNodeClick(null);
      if (onLinkClick) onLinkClick(null);
    }
    canvasRef.current?._draw?.();
  };

  const handleZoomIn = () => { transformRef.current.k = Math.min(10, transformRef.current.k * 1.2); canvasRef.current?._draw?.(); };
  const handleZoomOut = () => { transformRef.current.k = Math.max(0.05, transformRef.current.k * 0.8); canvasRef.current?._draw?.(); };
  const handleResetZoom = () => { transformRef.current = { x: 0, y: 0, k: 0.5 }; canvasRef.current?._draw?.(); };

  return (
    <div className={styles.container} ref={containerRef}>
      <div className={styles.zoomControls}>
        <button className={styles.zoomButton} onClick={handleZoomIn} title="Zoom In">
          <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4"></path></svg>
        </button>
        <button className={styles.zoomButton} onClick={handleZoomOut} title="Zoom Out">
          <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M20 12H4"></path></svg>
        </button>
        <button className={styles.zoomButton} onClick={handleResetZoom} title="Reset View">
          <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8"></path><path d="M3 3v5h5"></path></svg>
        </button>
      </div>
      <canvas
        ref={canvasRef}
        className={styles.canvas}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onClick={handleClick}
      />
    </div>
  );
}
