import { NextResponse } from "next/server";

import { databaseService, uploadGraphs } from "@ssat/prisma";

import { parseBulkGraphRequestPayload } from "@/src/server/upload/utils";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const items = parseBulkGraphRequestPayload(body);

    await databaseService.connect();
    const result = await uploadGraphs(
      items.map(({ graph, options }) => ({ data: graph, options })),
      databaseService
    );

    return NextResponse.json(
      {
        ok: result.failed === 0,
        data: result,
      },
      { status: result.failed === 0 ? 200 : 207 }
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const lower = message.toLowerCase();
    const status =
      lower.includes("invalid") ||
      lower.includes("required") ||
      lower.includes("unsupported") ||
      lower.includes("must")
        ? 400
        : 500;
    return NextResponse.json(
      {
        ok: false,
        error: message,
      },
      { status }
    );
  }
}
