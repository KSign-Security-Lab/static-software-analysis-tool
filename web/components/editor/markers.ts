import type * as Monaco from "monaco-editor";

import { SEVERITY_LABEL, markerSeverity, type UiFinding } from "@/lib/model/finding";

/**
 * Findings as editor markers.
 *
 * A marker rather than a decoration, because a marker is what Monaco's own
 * problem plumbing understands: it gets the squiggle, the gutter icon, the
 * hover and the F8 walk for free, and they behave the way they do in every
 * other editor.
 */
export function applyMarkers(
  monaco: typeof Monaco,
  model: Monaco.editor.ITextModel,
  findings: UiFinding[],
): void {
  const markers = findings
    .filter((finding) => finding.primary.startLine > 0)
    .map<Monaco.editor.IMarkerData>((finding) => ({
      severity: markerSeverity(finding.severity),
      // Monaco is 1-based and so is the wire schema, so these pass straight
      // through. The `|| line` guards a zero end, which the agent can emit for
      // a single-line finding.
      startLineNumber: finding.primary.startLine,
      startColumn: finding.primary.startColumn || 1,
      endLineNumber: finding.primary.endLine || finding.primary.startLine,
      endColumn: finding.primary.endColumn || 1000,
      message: `${SEVERITY_LABEL[finding.severity]} · ${finding.title}\n\n${finding.explanation}`,
      source: finding.cwe ?? undefined,
    }));

  monaco.editor.setModelMarkers(model, "ssat", markers);
}

/**
 * The evidence trail, as decorations.
 *
 * Separate from markers on purpose: these are the *other* lines that explain a
 * finding, and squiggling them all would say five things are wrong when one
 * is. They light up only for the selected finding.
 */
export function evidenceDecorations(
  finding: UiFinding | null,
  path: string | null,
): Monaco.editor.IModelDeltaDecoration[] {
  if (!finding || !path) return [];

  return finding.evidence
    .filter((each) => each.span.file === path && each.span.startLine > 0)
    .map((each) => ({
      range: {
        startLineNumber: each.span.startLine,
        startColumn: 1,
        endLineNumber: each.span.endLine || each.span.startLine,
        endColumn: 1,
      },
      options: {
        isWholeLine: true,
        className: `ev-${each.role}`,
        marginClassName: `ev-margin-${each.role}`,
        hoverMessage: { value: each.note },
      },
    }));
}
