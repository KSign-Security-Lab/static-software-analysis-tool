import { NextResponse } from "next/server";

import { databaseService, uploadGraph } from "@ssat/prisma";

import { parseGraphRequestPayload } from "@/src/server/upload/utils";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { graph, options } = parseGraphRequestPayload(body);

    await databaseService.connect();
    const result = await uploadGraph(graph, options, databaseService);

    return NextResponse.json(
      {
        ok: true,
        data: result,
      },
      { status: result.isNew ? 201 : 200 }
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
