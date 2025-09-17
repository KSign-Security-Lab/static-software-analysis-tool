import { NextResponse } from "next/server";
import dfgHandler from "@/src/handlers/DFGHandler";
import cpgHandler from "@/src/handlers/CPGHandler";
import { type CPGRoot } from "@ssat/core";

export async function POST(req: Request) {
  try {
    const formData = await req.formData();

    // Get input from form data - can be C source or CPG data
    const file = formData.get("file");
    const code = formData.get("code");
    const cpgData = formData.get("cpgData");

    let cpgInput: CPGRoot;

    // Check if CPG data is provided directly
    if (cpgData && typeof cpgData === "string") {
      try {
        cpgInput = JSON.parse(cpgData) as CPGRoot;
      } catch {
        return NextResponse.json(
          {
            status: 400,
            ok: false,
            error: "Invalid CPG data provided.",
          },
          { status: 400 }
        );
      }
    } else {
      // Generate CPG from C source
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
            error: "No input provided. Upload a file, paste code, or provide CPG data.",
          },
          { status: 400 }
        );
      }

      // Generate CPG data using CPGHandler
      cpgInput =
        file && file instanceof File ? await cpgHandler.getCPGDataFromCFile(cSource, filename) : await cpgHandler.getCPGDataFromCSource(cSource);
    }

    // Generate DFG from CPG data
    const dfgData = await dfgHandler.generateDFG(cpgInput);

    return NextResponse.json({
      status: 200,
      ok: true,
      message: "DFG generation completed successfully.",
      data: dfgData,
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
