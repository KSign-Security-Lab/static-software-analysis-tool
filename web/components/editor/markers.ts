import type * as Monaco from "monaco-editor";

import { SEVERITY_LABEL, STANDING_LABEL, markerSeverity, standingOf, type UiFinding } from "@/lib/model/finding";

export function applyMarkers(
  monaco: typeof Monaco,
  model: Monaco.editor.ITextModel,
  findings: UiFinding[],
): void {
  const markers = findings
    .filter((finding) => finding.primary.startLine > 0)
    .map<Monaco.editor.IMarkerData>((finding) => ({
      severity: markerSeverity(finding.severity),
      startLineNumber: finding.primary.startLine,
      startColumn: finding.primary.startColumn || 1,
      endLineNumber: finding.primary.endLine || finding.primary.startLine,
      endColumn: finding.primary.endColumn || 1000,
      message: [
        [SEVERITY_LABEL[finding.severity], standingLabel(finding), finding.title].filter(Boolean).join(" · "),
        finding.explanation,
        finding.remediation ? `고치는 방법\n${finding.remediation}` : "",
      ]
        .filter(Boolean)
        .join("\n\n"),
      source: finding.cwe ?? undefined,
    }));

  monaco.editor.setModelMarkers(model, "ssat", markers);
}

function standingLabel(finding: UiFinding): string {
  const standing = standingOf(finding);
  return standing ? STANDING_LABEL[standing] : "";
}

export function quickFixes(
  monaco: typeof Monaco,
  model: Monaco.editor.ITextModel,
  findings: UiFinding[],
  range: Monaco.IRange,
): Monaco.languages.CodeActionList {
  const actions = findings
    .filter((finding) => finding.replacement && finding.primary.startLine > 0)
    .filter((finding) => finding.primary.startLine <= range.endLineNumber)
    .filter((finding) => (finding.primary.endLine || finding.primary.startLine) >= range.startLineNumber)
    .map<Monaco.languages.CodeAction>((finding) => {
      const endLine = finding.primary.endLine || finding.primary.startLine;
      return {
        title: `이대로 고치기 · ${(finding.remediation ?? finding.title).split("\n")[0]}`,
        kind: "quickfix",
        isPreferred: true,
        diagnostics: [],
        edit: {
          edits: [
            {
              resource: model.uri,
              versionId: model.getVersionId(),
              textEdit: {
                range: {
                  startLineNumber: finding.primary.startLine,
                  startColumn: 1,
                  endLineNumber: endLine,
                  endColumn: model.getLineMaxColumn(endLine),
                },
                text: finding.replacement!,
              },
            },
          ],
        },
      };
    });

  return { actions, dispose: () => {} };
}

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
