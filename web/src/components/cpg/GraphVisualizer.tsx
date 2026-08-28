import React, { useEffect, useRef, useState, useCallback } from "react";
import BaseGraphVisualizer, { BaseNode, BaseLink } from "../common/BaseGraphVisualizer";
import styles from "./GraphVisualizer.module.css";

interface GraphVisualizerProps {
  data: unknown;
  onNodeClick: (node: BaseNode | null) => void;
}

export default function GraphVisualizer({ data, onNodeClick }: GraphVisualizerProps) {
  const [nodes, setNodes] = useState<BaseNode[]>([]);
  const [links, setLinks] = useState<BaseLink[]>([]);
  
  // Edge Filtering State
  const [edgeFilters, setEdgeFilters] = useState<Record<string, boolean>>({});
  const [edgeTypes, setEdgeTypes] = useState<string[]>([]);
  
  const selectedNodeRef = useRef<BaseNode | null>(null);
  const activeNeighborsRef = useRef<Set<BaseNode>>(new Set());

  useEffect(() => {
    const extractValue = (obj: unknown): any => {
      if (obj && typeof obj === 'object') {
        const o = obj as Record<string, unknown>;
        if (o["@value"] !== undefined) {
          let val = o["@value"];
          if (val && typeof val === 'object' && (val as any)["@value"] !== undefined) {
              val = (val as any)["@value"];
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
      const d = data as Record<string, any>;
      if (d["@type"] === "tinker:graph" && d["@value"]) {
        parsedNodes = d["@value"].vertices || [];
        parsedLinks = d["@value"].edges || [];
      } else {
        parsedNodes = d.nodes || [];
        parsedLinks = d.links || d.edges || [];
      }
    }

    const initNodes: BaseNode[] = parsedNodes.map((n, i) => {
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
        text = '';
      }

      let displayLabel = text ? `[${typeLabel}] ${text}` : `[${typeLabel}]`;
      if (displayLabel.length > 35) {
        displayLabel = displayLabel.substring(0, 32) + '...';
      }

      return {
        ...n,
        id,
        _id: id,
        x: 0,
        y: 0,
        color: n.color || '#3b82f6',
        label: displayLabel
      };
    });

    const nodeMap = new Map(initNodes.map(n => [n._id, n]));
    const types = new Set<string>();

    const initLinks: BaseLink[] = parsedLinks.map(l => {
      const srcId = extractValue(l.source || l.src || l.from || l.outV);
      const tgtId = extractValue(l.target || l.dst || l.to || l.inV);
      const source = nodeMap.get(srcId)!;
      const target = nodeMap.get(tgtId)!;
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
    const astAdj = new Map<BaseNode, BaseNode[]>();
    const inDegree = new Map<BaseNode, number>();
    
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

    const roots = initNodes.filter(n => inDegree.get(n) === 0);
    if (roots.length === 0 && initNodes.length > 0) roots.push(initNodes[0]);

    const horizontalGap = 40;
    const verticalGap = 80;
    const MAX_PER_ROW = 5;
    
    const boundsW = new Map<BaseNode, number>();
    const boundsH = new Map<BaseNode, number>();

    const calcBounds = (node: BaseNode, visited: Set<BaseNode>) => {
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
      
      totalH -= verticalGap;
      boundsW.set(node, maxTotalW);
      boundsH.set(node, totalH);
    };

    const visitedCalc = new Set<BaseNode>();
    roots.forEach(r => calcBounds(r, visitedCalc));

    let totalTreeWidth = 0;
    roots.forEach(r => {
      if (boundsW.has(r)) {
        totalTreeWidth += boundsW.get(r)! + horizontalGap * 2;
      }
    });

    const assignCoords = (node: BaseNode, startX: number, startY: number, visited: Set<BaseNode>) => {
      if (visited.has(node)) return;
      visited.add(node);

      const bW = boundsW.get(node) || node._layoutW!;
      node.x = startX + bW / 2;
      node.y = startY + node._layoutH! / 2;

      const children = astAdj.get(node) || [];
      const strictlyValid = children.filter(c => boundsW.has(c) && !visited.has(c));
      
      if (strictlyValid.length === 0) return;

      let currentY = startY + node._layoutH! + verticalGap;
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

    const visitedAssign = new Set<BaseNode>();
    let currentStartX = 400 - totalTreeWidth / 2;

    roots.forEach(r => {
      if (boundsW.has(r)) {
        const w = boundsW.get(r)!;
        assignCoords(r, currentStartX, 100, visitedAssign);
        currentStartX += w + horizontalGap * 2;
      }
    });

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

    setEdgeTypes(sortedTypes);
    setEdgeFilters(initialFilters);
    setNodes(initNodes);
    setLinks(initLinks);
  }, [data]);

  const toggleFilter = (type: string) => {
    setEdgeFilters(prev => ({ ...prev, [type]: !prev[type] }));
  };

  const activeLinks = links.filter(l => edgeFilters[l.label]);

  const handleNodeClick = useCallback((node: BaseNode | null) => {
    selectedNodeRef.current = node;
    if (node) {
      const neighbors = new Set<BaseNode>();
      neighbors.add(node);
      activeLinks.forEach(l => {
        if (l.source === node) neighbors.add(l.target);
        if (l.target === node) neighbors.add(l.source);
      });
      activeNeighborsRef.current = neighbors;
    } else {
      activeNeighborsRef.current = new Set();
    }
    onNodeClick(node);
  }, [activeLinks, onNodeClick]);

  const renderLink = useCallback((ctx: CanvasRenderingContext2D, link: BaseLink, k: number) => {
    if (!edgeFilters[link.label]) return;
    
    const isSelected = selectedNodeRef.current;
    let alpha = 1;
    if (isSelected) {
      alpha = (link.source === isSelected || link.target === isSelected) ? 1 : 0.1;
    }

    ctx.lineWidth = 1 / k;
    ctx.beginPath();
    ctx.moveTo(link.source.x, link.source.y);
    
    if (link.label === 'AST') {
      ctx.strokeStyle = `rgba(59, 130, 246, ${0.5 * alpha})`;
      ctx.lineTo(link.target.x, link.target.y);
    } else {
      ctx.strokeStyle = link.label === 'CFG' ? `rgba(239, 68, 68, ${0.4 * alpha})` : `rgba(156, 163, 175, ${0.5 * alpha})`;
      const midX = (link.source.x + link.target.x) / 2;
      const midY = (link.source.y + link.target.y) / 2 - 80;
      ctx.quadraticCurveTo(midX, midY, link.target.x, link.target.y);
    }
    ctx.stroke();

    if (k > 0.8 && link.label !== 'AST' && alpha > 0.5) {
      const midX = (link.source.x + link.target.x) / 2;
      const midY = (link.source.y + link.target.y) / 2 - 40;
      ctx.fillStyle = ctx.strokeStyle;
      ctx.font = `${8 / k}px sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText(link.label, midX, midY);
    }
  }, [edgeFilters]);

  const renderNode = useCallback((ctx: CanvasRenderingContext2D, node: BaseNode, isHovered: boolean, isSelected: boolean, k: number) => {
    const activeNeighbors = activeNeighborsRef.current;
    if (selectedNodeRef.current && !activeNeighbors.has(node)) return;

    const fontSize = 14;
    ctx.font = `${fontSize}px sans-serif`;
    const textWidth = ctx.measureText(node.label).width;
    
    const paddingX = 16;
    const paddingY = 12;
    const boxWidth = Math.max(textWidth + paddingX * 2, 80);
    const boxHeight = fontSize + paddingY * 2;
    
    node._boxW = boxWidth;
    node._boxH = boxHeight;
    
    ctx.beginPath();
    if (ctx.roundRect) {
        ctx.roundRect(node.x - boxWidth/2, node.y - boxHeight/2, boxWidth, boxHeight, 4);
    } else {
        ctx.rect(node.x - boxWidth/2, node.y - boxHeight/2, boxWidth, boxHeight);
    }
    
    let nodeColor = (node as any).color || '#3b82f6';
    if (isHovered) nodeColor = "#ef4444";
    if (isSelected) nodeColor = "#10b981";

    ctx.fillStyle = nodeColor;
    ctx.fill();
    
    ctx.lineWidth = (isSelected ? 3 : 1) / k;
    ctx.strokeStyle = isSelected ? "#059669" : "#ffffff";
    ctx.stroke();
    
    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(node.label, node.x, node.y);
  }, []);

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
        </div>
      </div>
      
      <BaseGraphVisualizer
        nodes={nodes}
        links={links}
        onNodeClick={handleNodeClick}
        renderNode={renderNode}
        renderLink={renderLink}
      />
    </div>
  );
}
