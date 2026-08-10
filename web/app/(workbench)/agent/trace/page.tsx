import { redirect } from "next/navigation";

/**
 * 트레이스 was a separate route until it stopped being a separate place.
 *
 * The graph is a tab in the centre of /agent now, beside the code, over the
 * same dock. Kept as a redirect because links and bookmarks exist: the run and
 * the selection carry across, and `centre=graph` lands on the view the old
 * path meant.
 */
export default async function TraceRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(await searchParams)) {
    if (typeof value === "string") params.set(key, value);
  }
  params.set("centre", "graph");
  redirect(`/agent?${params.toString()}`);
}
