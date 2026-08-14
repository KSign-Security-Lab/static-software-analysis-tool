/**
 * How long ago, coarsely.
 *
 * Lifted out of `RunHistory` when the editor wanted the same sentence for its
 * own save time. A run bar and an editor header are both places where a
 * timestamp to the second is noise: what is being asked is "recently, or a while
 * back", and two components answering that differently would be two vocabularies
 * for one idea.
 *
 * Takes epoch *seconds*, which is what the API sends.
 */
export function ago(at: number): string {
  const seconds = Math.max(0, Date.now() / 1000 - at);
  if (seconds < 90) return "방금";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.round(hours / 24)}일 전`;
}
