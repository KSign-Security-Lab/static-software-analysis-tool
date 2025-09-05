import { TreeNode } from "../types/cpg";
import { ASTNodes } from "../types/node";

export class TreeToText {
  private blacklistProps: Set<string>;

  /**
   * @param blacklistProps Array of node property names to exclude from text output.
   *                       Defaults to empty array (no extra keys blacklisted).
   */
  constructor(blacklistProps: string[] = []) {
    this.blacklistProps = new Set(blacklistProps);
  }

  /**
   * Entry: convert an ASTNodes into a text tree.
   */
  public convert(root: ASTNodes): string {
    const lines: string[] = [];
    this.buildLines(root, "", true, lines, 0);
    return lines.join("\n");
  }

  /**
   * Recursive helper to build lines.
   * @param node Current node.
   * @param prefix Accumulated prefix string (spaces and vertical bars).
   * @param isLast Whether this node is the last child of its parent.
   * @param lines Collector for output lines.
   * @param depth Current depth (root=0, children=1, ...).
   */
  private buildLines(node: ASTNodes | TreeNode, prefix: string, isLast: boolean, lines: string[], depth: number): void {
    let typeName: string;
    if ("nodeType" in node && typeof node.nodeType === "string") {
      typeName = node.nodeType;
    } else if ("label" in node && typeof node.label === "string") {
      typeName = node.label;
    } else {
      typeName = "Unknown";
    }
    const connector = depth === 0 ? "" : isLast ? "└── " : "├── ";
    const attrText = this.formatAttributes(node);
    lines.push(`${prefix}${connector}${typeName}${attrText}`);

    const newPrefix = depth === 0 ? "" : prefix + (isLast ? "    " : "│   ");
    const children = Array.isArray(node.children) ? node.children : [];
    children.forEach((child, idx) => {
      const last = idx === children.length - 1;
      this.buildLines(child, newPrefix, last, lines, depth + 1);
    });
  }

  /**
   * Format all keys except nodeType, label, children, and any in blacklistProps into "(k=v, ...)".
   */
  private formatAttributes(node: ASTNodes | TreeNode): string {
    const parts: string[] = [];
    for (const [key, value] of Object.entries(node)) {
      if (key === "nodeType" || key === "label" || key === "children") {
        continue;
      }
      if (this.blacklistProps.has(key)) {
        continue;
      }
      if (value === undefined || typeof value === "function") {
        continue;
      }
      let strVal: string;
      if (value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
        strVal = String(value);
      } else {
        // convert to string without deep JSON.stringify to avoid huge output
        strVal = String(value);
      }
      parts.push(`${key}=${strVal}`);
    }
    if (parts.length === 0) return "";
    return ` (${parts.join(", ")})`;
  }
}
