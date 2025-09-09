import { NextResponse } from "next/server";
import templateHandler from "../../../src/handlers/TemplateHandler";
import cpgHandler from "../../../src/handlers/CPGHandler";
import { CPGRoot } from "@ssat/core/types/cpg";

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
      cpgInput = await cpgHandler.getCPGData(cSource, {
        filename,
        cleanAfter: false,
        cleanupTempDir: false,
      });
    }

    // Generate template from CPG data
    const templateData = await templateHandler.generateTemplate(cpgInput, {
      includeTextLines: true,
      includeFlattened: true,
    });

    return NextResponse.json({
      status: 200,
      ok: true,
      message: "Template generation completed successfully.",
      data: templateData.templateResult,
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
