"use client";

import dynamic from "next/dynamic";

const DiffView = dynamic(() => import("./DiffView"), {
  ssr: false,
  loading: () => <p className="p-3 text-2xs text-ink-faint">비교하는 중…</p>,
});

export default DiffView;
