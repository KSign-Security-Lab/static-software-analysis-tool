import { redirect } from "next/navigation";

/** The old name. "Studio" was borrowed from LangGraph; it is a tab now. */
export default function StudioRedirect() {
  redirect("/agent?centre=graph");
}
