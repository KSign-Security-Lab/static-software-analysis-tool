import type { ReactNode } from "react";

import InspectShell from "@/features/inspect/InspectShell";

export default function InspectLayout({ children }: { children: ReactNode }) {
  return <InspectShell>{children}</InspectShell>;
}

export const dynamic = "force-dynamic";
