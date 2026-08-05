import { redirect } from "next/navigation";

/** The old name. "Studio" was borrowed from LangGraph; the dock tab says TRACE. */
export default function StudioRedirect() {
  redirect("/agent/trace");
}
