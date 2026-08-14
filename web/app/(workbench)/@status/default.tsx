/**
 * No status strip, for every perspective that has not asked for one.
 *
 * A parallel-route slot needs a `default.tsx` at every level or a soft
 * navigation leaves it showing whatever it rendered last. Null rather than a
 * placeholder: an empty strip is still a strip, and the row it sits in
 * collapses to nothing when this renders nothing.
 */
export default function StatusDefault() {
  return null;
}
