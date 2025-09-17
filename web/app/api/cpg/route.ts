import cpgHandler from "@/src/handlers/CPGHandler";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  try {
    const formData = await req.formData();

    // Get input from form data
    const file = formData.get("file");
    const code = formData.get("code");

    let cSource: string;
    let filename: string;

    if (file && file instanceof File) {
      cSource = await file.text();
      filename = file.name || "input.c";
    } else if (typeof code === "string" && code.trim().length > 0) {
      cSource = code;
      filename = "input.c";
    } else {
      return NextResponse.json(
        {
          status: 400,
          ok: false,
          error: "No input provided. Upload a file or paste code.",
        },
        { status: 400 }
      );
    }

    // Generate CPG data using CPGHandler
    const cpgData =
      file && file instanceof File ? await cpgHandler.getCPGDataFromCFile(cSource, filename) : await cpgHandler.getCPGDataFromCSource(cSource);

    return NextResponse.json({
      status: 200,
      ok: true,
      message: "CPG generation completed successfully.",
      data: cpgData,
    });
  } catch (error) {
    return NextResponse.json(
      {
        status: 500,
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      },
      { status: 500 }
    );
  }
}
