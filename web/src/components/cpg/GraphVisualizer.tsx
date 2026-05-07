"use client";

import React, { useEffect, useRef, useState } from "react";
import styles from "./GraphVisualizer.module.css";

interface GraphVisualizerProps {
  data: any;
  onNodeClick: (node: any) => void;
}

// Basic Force-Directed Graph implementation on HTML5 Canvas
export default function GraphVisualizer({ data, onNodeClick }: GraphVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>(0);
  
  const [nodes, setNodes] = useState<any[]>([]);
  const [links, setLinks] = useState<any[]>([]);
  
  // Edge Filtering State
  const [edgeFilters, setEdgeFilters] = useState<Record<string, boolean>>({});
  const [edgeTypes, setEdgeTypes] = useState<string[]>([]);
  
  // View transform
  const transformRef = useRef({ x: 0, y: 0, k: 0.5 });
  const isDraggingRef = useRef(false);
  const lastMouseRef = useRef({ x: 0, y: 0 });
  const hoveredNodeRef = useRef<any>(null);
  const selectedNodeRef = useRef<any>(null);
  const activeNeighborsRef = useRef<Set<any>>(new Set());

  useEffect(() => {
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

    let parsedNodes: any[] = [];
    let parsedLinks: any[] = [];

    if (Array.isArray(data)) {
      parsedNodes = data;
    } else if (data && typeof data === 'object') {
      if (data["@type"] === "tinker:graph" && data["@value"]) {
        parsedNodes = data["@value"].vertices || [];
        parsedLinks = data["@value"].edges || [];
      } else {
        parsedNodes = data.nodes || [];
        parsedLinks = data.links || data.edges || [];
      }
    }

    const initNodes = parsedNodes.map((n, i) => {
      const rawId = extractValue(n.id);
      const id = rawId !== undefined ? rawId : i;
      
      const typeLabel = n.label || n._label || 'UNKNOWN';
      let text = n.name || String(id);
      
      if (n.properties) {
        if (n.properties.CODE) {
          text = extractValue(n.properties.CODE);
        } else if (n.properties.NAME) {
          text = extractValue(n.properties.NAME);
        }
      }

      if (typeof text === 'object') {
        text = ''; // Prevent [object Object]
      }

      // Format as "[TYPE] text" to give context
      let displayLabel = text ? `[${typeLabel}] ${text}` : `[${typeLabel}]`;
      
      // truncate long text
      if (displayLabel.length > 35) {
        displayLabel = displayLabel.substring(0, 32) + '...';
      }

      return {
        ...n,
        _id: id,
        x: 0,
        y: 0,
        color: n.color || '#3b82f6',
        label: displayLabel
      };
    });

    const nodeMap = new Map(initNodes.map(n => [n._id, n]));
    const types = new Set<string>();

    const initLinks = parsedLinks.map(l => {
      const srcId = extractValue(l.source || l.src || l.from || l.outV);
      const tgtId = extractValue(l.target || l.dst || l.to || l.inV);
      const source = typeof l.source === 'object' ? l.source : nodeMap.get(srcId);
      const target = typeof l.target === 'object' ? l.target : nodeMap.get(tgtId);
      const label = String(l.label || l._label || l.type || 'UNKNOWN');
      types.add(label);
      return { ...l, source, target, label };
    }).filter(l => l.source && l.target);

    // Initial Filters: Only AST and CFG are true by default
    const initialFilters: Record<string, boolean> = {};
    const sortedTypes = Array.from(types).sort();
    sortedTypes.forEach(t => {
      initialFilters[t] = t === 'AST' || t === 'CFG' || t === 'REF';
    });

    // --- HIERARCHICAL TREE LAYOUT ALGORITHM ---
    const astAdj = new Map<any, any[]>();
    const inDegree = new Map<any, number>();
    
    initNodes.forEach(n => {
      astAdj.set(n, []);
      inDegree.set(n, 0);
    });

    initLinks.forEach(l => {
      if (l.label === 'AST') {
        astAdj.get(l.source)?.push(l.target);
        inDegree.set(l.target, (inDegree.get(l.target) || 0) + 1);
      }
    });

    // --- HIERARCHICAL TREE LAYOUT ALGORITHM (Grid-Wrapped Top-Down) ---
    const roots = initNodes.filter(n => inDegree.get(n) === 0);
    if (roots.length === 0 && initNodes.length > 0) roots.push(initNodes[0]);

    const horizontalGap = 40;
    const verticalGap = 80;
    const MAX_PER_ROW = 5; // flexible wrapping to prevent wide walls
    
    const boundsW = new Map<any, number>();
    const boundsH = new Map<any, number>();

    // 1. Calculate true bounding boxes with grid-wrapping
    const calcBounds = (node: any, visited: Set<any>) => {
      if (visited.has(node)) return;
      visited.add(node);

      node._layoutW = Math.max(node.label.length * 7.5 + 32, 80);
      node._layoutH = 40;

      const children = astAdj.get(node) || [];
      const validChildren = children.filter(c => !visited.has(c));

      if (validChildren.length === 0) {
        boundsW.set(node, node._layoutW);
        boundsH.set(node, node._layoutH);
        return;
      }

      validChildren.forEach(c => calcBounds(c, visited));
      const strictlyValid = validChildren.filter(c => boundsW.has(c));

      let totalH = node._layoutH + verticalGap;
      let maxTotalW = node._layoutW;
      
      let currentRowW = 0;
      let currentRowH = 0;
      
      strictlyValid.forEach((c, i) => {
        const cw = boundsW.get(c)!;
        const ch = boundsH.get(c)!;
        
        currentRowW += cw + horizontalGap;
        if (ch > currentRowH) currentRowH = ch;
        
        if ((i + 1) % MAX_PER_ROW === 0 || i === strictlyValid.length - 1) {
          currentRowW -= horizontalGap;
          if (currentRowW > maxTotalW) maxTotalW = currentRowW;
          totalH += currentRowH + verticalGap;
          currentRowW = 0;
          currentRowH = 0;
        }
      });
      
      totalH -= verticalGap; // remove trailing gap
      
      boundsW.set(node, maxTotalW);
      boundsH.set(node, totalH);
    };

    const visitedCalc = new Set<any>();
    roots.forEach(r => calcBounds(r, visitedCalc));

    let totalTreeWidth = 0;
    roots.forEach(r => {
      if (boundsW.has(r)) {
        totalTreeWidth += boundsW.get(r)! + horizontalGap * 2;
      }
    });

    // 2. Assign coordinates recursively based on bounds
    const assignCoords = (node: any, startX: number, startY: number, visited: Set<any>) => {
      if (visited.has(node)) return;
      visited.add(node);

      const bW = boundsW.get(node) || node._layoutW;
      node.x = startX + bW / 2;
      node.y = startY + node._layoutH / 2;

      const children = astAdj.get(node) || [];
      const strictlyValid = children.filter(c => boundsW.has(c) && !visited.has(c));
      
      if (strictlyValid.length === 0) return;

      let currentY = startY + node._layoutH + verticalGap;
      let rowStartIdx = 0;
      
      while (rowStartIdx < strictlyValid.length) {
        const rowChildren = strictlyValid.slice(rowStartIdx, rowStartIdx + MAX_PER_ROW);
        
        let rowW = 0;
        let rowMaxH = 0;
        rowChildren.forEach(c => {
          rowW += boundsW.get(c)! + horizontalGap;
          const ch = boundsH.get(c)!;
          if (ch > rowMaxH) rowMaxH = ch;
        });
        rowW -= horizontalGap;
        
        let currentX = startX + (bW - rowW) / 2;
        
        rowChildren.forEach(c => {
          const cw = boundsW.get(c)!;
          assignCoords(c, currentX, currentY, visited);
          currentX += cw + horizontalGap;
        });
        
        currentY += rowMaxH + verticalGap;
        rowStartIdx += MAX_PER_ROW;
      }
    };

    const visitedAssign = new Set<any>();
    const cx = (canvasRef.current?.clientWidth || 800) / 2;
    let currentStartX = cx - totalTreeWidth / 2;

    roots.forEach(r => {
      if (boundsW.has(r)) {
        const w = boundsW.get(r)!;
        assignCoords(r, currentStartX, 100, visitedAssign);
        currentStartX += w + horizontalGap * 2;
      }
    });

    // Handle any disconnected components
    initNodes.forEach(n => {
      if (!visitedAssign.has(n)) {
        if (!n._layoutW) n._layoutW = Math.max(n.label.length * 7.5 + 32, 80);
        if (!n._layoutH) n._layoutH = 40;
        n.y = 100 + n._layoutH / 2;
        n.x = currentStartX + n._layoutW / 2;
        currentStartX += n._layoutW + horizontalGap;
        visitedAssign.add(n);
      }
    });
    // --- END LAYOUT ---

    setEdgeTypes(sortedTypes);
    setEdgeFilters(initialFilters);
    setNodes(initNodes);
    setLinks(initLinks);

    transformRef.current = { x: 0, y: 0, k: 0.5 }; // start zoomed out slightly
  }, [data]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || nodes.length === 0) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.save();
      
      const { x, y, k } = transformRef.current;
      ctx.translate(x, y);
      ctx.scale(k, k);

      // Frustum culling boundaries
      const viewMinX = -x / k;
      const viewMaxX = (canvas.width - x) / k;
      const viewMinY = -y / k;
      const viewMaxY = (canvas.height - y) / k;
      
      const isVisible = (nx: number, ny: number) => 
        nx >= viewMinX - 150 && nx <= viewMaxX + 150 && 
        ny >= viewMinY - 150 && ny <= viewMaxY + 150;

      // Find neighbors of selected node
      const activeNeighbors = new Set<any>();
      if (selectedNodeRef.current) {
        activeNeighbors.add(selectedNodeRef.current);
        links.forEach(l => {
          if (edgeFilters[l.label]) {
            if (l.source === selectedNodeRef.current) activeNeighbors.add(l.target);
            if (l.target === selectedNodeRef.current) activeNeighbors.add(l.source);
          }
        });
      }
      activeNeighborsRef.current = activeNeighbors;

      // Helper to check if element should be faded
      const getAlpha = (node1: any, node2?: any) => {
        if (!selectedNodeRef.current) return 1; // no selection, full opacity
        if (node2) {
          // It's a link
          if (node1 === selectedNodeRef.current || node2 === selectedNodeRef.current) return 1;
        } else {
          // It's a node
          if (activeNeighbors.has(node1)) return 1;
        }
        return 0.1; // heavily faded
      };

      // Draw links
      ctx.lineWidth = 1 / k;
      for (const link of links) {
        if (!edgeFilters[link.label]) continue;
        
        if (isVisible(link.source.x, link.source.y) || isVisible(link.target.x, link.target.y)) {
          const alpha = getAlpha(link.source, link.target);
          
          ctx.beginPath();
          ctx.moveTo(link.source.x, link.source.y);
          
          if (link.label === 'AST') {
            ctx.strokeStyle = `rgba(59, 130, 246, ${0.5 * alpha})`; // Straight blue line for AST
            ctx.lineTo(link.target.x, link.target.y);
          } else {
            // Draw curved line for non-AST edges to distinguish them
            ctx.strokeStyle = link.label === 'CFG' ? `rgba(239, 68, 68, ${0.4 * alpha})` : `rgba(156, 163, 175, ${0.5 * alpha})`;
            const midX = (link.source.x + link.target.x) / 2;
            const midY = (link.source.y + link.target.y) / 2 - 80; // Curve upwards more
            ctx.quadraticCurveTo(midX, midY, link.target.x, link.target.y);
          }
          ctx.stroke();
          
          // Draw edge label if zoomed in enough
          if (k > 0.8 && link.label !== 'AST') {
             const midX = (link.source.x + link.target.x) / 2;
             const midY = (link.source.y + link.target.y) / 2 - 40;
             ctx.fillStyle = ctx.strokeStyle;
             ctx.font = `${8 / k}px sans-serif`;
             ctx.textAlign = "center";
             ctx.fillText(link.label, midX, midY);
          }
        }
      }

      // Draw nodes as boxes
      for (const node of nodes) {
        if (!isVisible(node.x, node.y)) continue;
        if (selectedNodeRef.current && !activeNeighbors.has(node)) continue; // Completely hide non-neighbors to reduce crowding

        const fontSize = 14;
        ctx.font = `${fontSize}px sans-serif`;
        const textWidth = ctx.measureText(node.label).width;
        
        const paddingX = 16;
        const paddingY = 12;
        const boxWidth = Math.max(textWidth + paddingX * 2, 80);
        const boxHeight = fontSize + paddingY * 2;
        
        // Save for hit detection
        node._boxW = boxWidth;
        node._boxH = boxHeight;
        
        ctx.beginPath();
        if (ctx.roundRect) {
            ctx.roundRect(node.x - boxWidth/2, node.y - boxHeight/2, boxWidth, boxHeight, 4);
        } else {
            ctx.rect(node.x - boxWidth/2, node.y - boxHeight/2, boxWidth, boxHeight);
        }
        
        let nodeColor = node.color || '#3b82f6';
        if (hoveredNodeRef.current === node) nodeColor = "#ef4444";
        if (selectedNodeRef.current === node) nodeColor = "#10b981"; // Emerald green for selected

        ctx.fillStyle = nodeColor;
        ctx.fill();
        
        ctx.lineWidth = (selectedNodeRef.current === node ? 3 : 1) / k; // keep border visually consistent thickness
        ctx.strokeStyle = selectedNodeRef.current === node ? "#059669" : "#ffffff";
        ctx.stroke();
        
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(node.label, node.x, node.y);
      }
      
      ctx.restore();
    };

    const resize = () => {
      const rect = canvas.parentElement?.getBoundingClientRect();
      if (rect) {
        canvas.width = rect.width;
        canvas.height = rect.height;
        draw(); // Redraw immediately on resize
      }
    };
    window.addEventListener('resize', resize);
    resize();

    // Replace requestAnimationFrame with a single draw since layout is static!
    // We only need an animation loop if dragging/panning is continuous, but React events drive it
    draw();
    
    // Store draw function on ref so events can trigger redraws without re-running useEffect
    (canvas as any)._draw = draw;

    return () => {
      window.removeEventListener('resize', resize);
      delete (canvas as any)._draw;
    };
  }, [nodes, links, edgeFilters]);

  // Event handlers
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const scaleFactor = e.deltaY > 0 ? 0.9 : 1.1;
    const { x, y, k } = transformRef.current;
    
    const rect = canvasRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const newK = Math.max(0.05, Math.min(10, k * scaleFactor));
    const newX = mx - (mx - x) * (newK / k);
    const newY = my - (my - y) * (newK / k);
    
    transformRef.current = { x: newX, y: newY, k: newK };
    if ((canvasRef.current as any)?._draw) (canvasRef.current as any)._draw();
  };

  const getMousePos = (e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const getTransformedMousePos = (e: React.MouseEvent) => {
    const { x: mx, y: my } = getMousePos(e);
    const { x, y, k } = transformRef.current;
    return { tx: (mx - x) / k, ty: (my - y) / k };
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    isDraggingRef.current = true;
    lastMouseRef.current = getMousePos(e);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const pos = getMousePos(e);
    if (isDraggingRef.current) {
      const dx = pos.x - lastMouseRef.current.x;
      const dy = pos.y - lastMouseRef.current.y;
      transformRef.current.x += dx;
      transformRef.current.y += dy;
      lastMouseRef.current = pos;
      if ((canvasRef.current as any)?._draw) (canvasRef.current as any)._draw();
    } else {
      const { tx, ty } = getTransformedMousePos(e);
      let found = null;
      for (let i = nodes.length - 1; i >= 0; i--) {
        const node = nodes[i];
        if (selectedNodeRef.current && !activeNeighborsRef.current.has(node)) continue;
        
        // Use dynamically calculated bounds if available, else approximate
        const boxW = node._boxW || 120;
        const boxH = node._boxH || 40;
        
        if (tx >= node.x - boxW/2 && tx <= node.x + boxW/2 && ty >= node.y - boxH/2 && ty <= node.y + boxH/2) {
          found = node;
          break;
        }
      }
      if (hoveredNodeRef.current !== found) {
        hoveredNodeRef.current = found;
        if (canvasRef.current) {
          canvasRef.current.style.cursor = found ? 'pointer' : 'grab';
          (canvasRef.current as any)._draw();
        }
      }
    }
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
    if (canvasRef.current && !hoveredNodeRef.current) {
      canvasRef.current.style.cursor = 'grab';
    }
  };

  const handleClick = () => {
    if (hoveredNodeRef.current) {
      if (selectedNodeRef.current === hoveredNodeRef.current) {
         selectedNodeRef.current = null; // deselect
         onNodeClick(null);
      } else {
         selectedNodeRef.current = hoveredNodeRef.current;
         onNodeClick(hoveredNodeRef.current);
      }
      if ((canvasRef.current as any)?._draw) (canvasRef.current as any)._draw();
    }
  };

  const toggleFilter = (type: string) => {
    setEdgeFilters(prev => ({ ...prev, [type]: !prev[type] }));
  };

  const handleZoomIn = () => {
    const { x, y, k } = transformRef.current;
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const newK = Math.min(10, k * 1.2);
    
    transformRef.current = {
      x: cx - (cx - x) * (newK / k),
      y: cy - (cy - y) * (newK / k),
      k: newK
    };
    if ((canvas as any)._draw) (canvas as any)._draw();
  };

  const handleZoomOut = () => {
    const { x, y, k } = transformRef.current;
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const newK = Math.max(0.05, k * 0.8);
    
    transformRef.current = {
      x: cx - (cx - x) * (newK / k),
      y: cy - (cy - y) * (newK / k),
      k: newK
    };
    if ((canvas as any)._draw) (canvas as any)._draw();
  };

  const handleResetZoom = () => {
    transformRef.current = { x: 0, y: 0, k: 1 };
    if ((canvasRef.current as any)?._draw) (canvasRef.current as any)._draw();
  };

  return (
    <div className={styles.container}>
      <div className={styles.filterPanel}>
        <div className={styles.filterHeader}>Edge Filters</div>
        <div className={styles.filterContent}>
          {edgeTypes.map(type => (
            <div key={type} className={styles.filterItem} onClick={() => toggleFilter(type)}>
              <span className={styles.filterLabel}>{type}</span>
              <input
                type="checkbox"
                className={styles.filterCheckbox}
                checked={!!edgeFilters[type]}
                readOnly
              />
            </div>
          ))}
          {edgeTypes.length === 0 && (
            <div style={{ padding: '1rem', color: '#6b7280', fontSize: '0.875rem' }}>
              No edges found.
            </div>
          )}
        </div>
      </div>
      
      <div className={styles.zoomControls}>
        <button className={styles.zoomButton} onClick={handleZoomIn} title="Zoom In">
          <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4"></path></svg>
        </button>
        <button className={styles.zoomButton} onClick={handleZoomOut} title="Zoom Out">
          <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M20 12H4"></path></svg>
        </button>
        <button className={styles.zoomButton} onClick={handleResetZoom} title="Reset View">
          <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8"></path><path strokeLinecap="round" strokeLinejoin="round" d="M3 3v5h5"></path></svg>
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
