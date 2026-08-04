import { redirect } from "next/navigation";

/** The agent is the primary section, so it is what the root opens. */
export default function Root() {
  redirect("/agent");
}
