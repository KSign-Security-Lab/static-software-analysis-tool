"use client";

import { labelColor } from "@/lib/layout";
import type { ViewNode } from "@/lib/types";

export default function NodePanel({ node }: { node: ViewNode | null }) {
  if (!node) {
    return (
      <aside className="nodepanel">
        <h3>노드 정보</h3>
        <p className="status">노드를 클릭하면 CPG 속성을 볼 수 있습니다.</p>
      </aside>
    );
  }
  const props = Object.entries(node.props).filter(
    ([k]) => !["NAME", "CODE", "LINE_NUMBER"].includes(k),
  );
  return (
    <aside className="nodepanel">
      <h3>노드 정보</h3>
      <div className="kv">
        <span className="k">label</span>
        <span className="v">
          <span className="chip" style={{ borderColor: labelColor(node.label), color: labelColor(node.label) }}>
            {node.label}
          </span>
        </span>
        <span className="k">id</span>
        <span className="v">{node.id}</span>
        {node.name && (
          <>
            <span className="k">name</span>
            <span className="v">{node.name}</span>
          </>
        )}
        {node.code && (
          <>
            <span className="k">code</span>
            <span className="v">{node.code}</span>
          </>
        )}
        {node.line !== "" && (
          <>
            <span className="k">line</span>
            <span className="v">{String(node.line)}</span>
          </>
        )}
      </div>
      {props.length > 0 && (
        <>
          <h3 style={{ marginTop: 18 }}>속성</h3>
          <div className="kv">
            {props.map(([k, v]) => (
              <PropRow key={k} k={k} v={v} />
            ))}
          </div>
        </>
      )}
    </aside>
  );
}

function PropRow({ k, v }: { k: string; v: unknown }) {
  const text =
    v === null || v === undefined
      ? "—"
      : typeof v === "object"
        ? JSON.stringify(v)
        : String(v);
  return (
    <>
      <span className="k">{k}</span>
      <span className="v">{text.length > 200 ? text.slice(0, 200) + "…" : text}</span>
    </>
  );
}
