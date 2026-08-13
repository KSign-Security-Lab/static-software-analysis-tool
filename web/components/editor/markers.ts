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
      // The fix on the hover, under the explanation. Monaco shows a marker's
      // message when you hover its squiggle, so this is where a reader already
      // looks -- and the lightbulb beside it is what actually applies it.
      message: [
        `${SEVERITY_LABEL[finding.severity]} · ${finding.title}`,
        finding.explanation,
        finding.remediation ? `고치는 방법\n${finding.remediation}` : "",
      ]
        .filter(Boolean)
        .join("\n\n"),
      source: finding.cwe ?? undefined,
    }));

  monaco.editor.setModelMarkers(model, "ssat", markers);
}

/**
 * The fix, as a quick fix on the squiggle.
 *
 * The fix used to live only at the bottom of a card in another pane. Monaco has
 * had the whole affordance for this since before we started: a marker owns a
 * squiggle, and a code action provider hangs a lightbulb off it -- so the fix
 * sits on the line it fixes, one keystroke away, undoable, exactly where anyone
 * who has used an editor already looks for it.
 *
 * The edit goes into the buffer rather than to the server. That is what makes it
 * undoable with the editor's own ⌘Z, and it means the write still happens through
 * the one save path everything else uses rather than a second way to modify a
 * file.
 *
 * Only findings that carry a replacement get one. `remediation.detail` on its own
 * is advice, and an action that opened a dialogue saying "here is some prose"
 * would be a lightbulb that lies about having a fix.
 */
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
        // The summary line only: `remediation` is summary and detail joined, and a
        // paragraph in a menu item is a menu item nobody can read.
        title: `이대로 고치기 · ${(finding.remediation ?? finding.title).split("\n")[0]}`,
        kind: "quickfix",
        // Marked preferred so ⌘. applies it without a menu when it is the only
        // thing on offer, which on a squiggled line it usually is.
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
