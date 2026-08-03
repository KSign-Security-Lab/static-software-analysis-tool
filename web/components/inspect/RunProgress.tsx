"use client";

/**
 * Chunk-by-chunk progress.
 *
 * A run takes minutes, so a spinner would be dishonest about what is happening.
 * This shows which unit is being analysed and how many remain, and the counts
 * keep true positives separate from what was dropped or refuted rather than
 * rolling everything into one number.
 */

export interface RunProgressProps {
  running: boolean;
  done: number;
  total: number;
  current: string | null;
  findings: number;
  error: string | null;
}

export function RunProgress({
  running,
  done,
  total,
  current,
  findings,
  error,
}: RunProgressProps) {
  if (error) {
    return (
      <div className="progress progress-error" role="alert">
        검사 실패: {error}
      </div>
    );
  }
  if (!running && done === 0) return null;

  const percent = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div className="progress">
      <div className="progress-bar" aria-hidden>
        <div className="progress-fill" style={{ width: `${percent}%` }} />
      </div>
      <div className="progress-text">
        {running ? (
          <>
            <span className="progress-count">
              {done} / {total} 청크
            </span>
            {current && <span className="progress-current">{current}</span>}
          </>
        ) : (
          <span className="progress-count">검사 완료 — {done} 청크</span>
        )}
        <span className="progress-findings">{findings}건 발견</span>
      </div>
    </div>
  );
}
