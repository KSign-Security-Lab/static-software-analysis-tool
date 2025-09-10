import { NextResponse } from "next/server";
import astHandler from "@/src/handlers/ASTHandler";
import cpgHandler from "@/src/handlers/CPGHandler";
import { CPGRoot } from "@ssat/core/types/cpg";
import { TemplateNodes } from "@ssat/core/types/node";

export async function POST(req: Request) {
  try {
    const formData = await req.formData();

    // Inputs may be C source, CPG JSON, or Template JSON
    const file = formData.get("file");
    const code = formData.get("code");
    const cpgData = formData.get("cpgData");
    const templateData = formData.get("templateData");

    // 1) If template is provided, use it directly
    if (typeof templateData === "string" && templateData.trim().length > 0) {
      let parsed: unknown;
      try {
        parsed = JSON.parse(templateData);
      } catch {
        return NextResponse.json({ status: 400, ok: false, error: "Invalid template data (JSON parse failed)." }, { status: 400 });
      }

      // Accept either a single function root or an array; pick the first if array
      const templateRoot: TemplateNodes = (Array.isArray(parsed) ? parsed[0] : parsed) as TemplateNodes;
      const astResult = await astHandler.getASTFromTemplate(templateRoot);
      return NextResponse.json({ status: 200, ok: true, message: "AST generated from template.", data: astResult });
    }

    // 2) If CPG is provided, derive template then AST
    if (typeof cpgData === "string" && cpgData.trim().length > 0) {
      let cpgInput: CPGRoot;
      try {
        cpgInput = JSON.parse(cpgData) as CPGRoot;
      } catch {
        return NextResponse.json({ status: 400, ok: false, error: "Invalid CPG data (JSON parse failed)." }, { status: 400 });
      }

      const astResult = await astHandler.getASTFromCPG(cpgInput);
      return NextResponse.json({ status: 200, ok: true, message: "AST generated from CPG.", data: astResult });
    }

    // 3) Otherwise, expect C source, generate CPG -> Template -> AST
    let cSource: string | undefined;
    let filename = "input.c";
    if (file && file instanceof File) {
      cSource = await file.text();
      filename = file.name || filename;
    } else if (typeof code === "string" && code.trim().length > 0) {
      cSource = code;
    }

    if (!cSource) {
      return NextResponse.json({ status: 400, ok: false, error: "No input provided. Supply template, CPG JSON, or C source." }, { status: 400 });
    }

    const cpgInput = await cpgHandler.getCPGData(cSource, { filename, cleanAfter: false, cleanupTempDir: false });
    const astResult = await astHandler.getASTFromCPG(cpgInput);

    return NextResponse.json({ status: 200, ok: true, message: "AST generated from C source.", data: astResult });
  } catch (error) {
    return NextResponse.json({ status: 500, ok: false, error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  }
}
