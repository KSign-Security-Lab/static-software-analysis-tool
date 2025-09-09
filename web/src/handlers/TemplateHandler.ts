// templateHandler.ts
import { validateCPGRoot } from "@ssat/core/cpg/validate/zod";
import { PlanationTool } from "@ssat/core/template/PlanationTool";
import { PostProcessor } from "@ssat/core/template/PostProcessor";
import { TemplateConverter } from "@ssat/core/template/TemplateConverter";
import { TemplateExtractor } from "@ssat/core/template/TemplateExtractor";
import { CPGRoot, TreeNode } from "@ssat/core/types/cpg";
import { TemplateFlattenedGraph, TemplateNodes } from "@ssat/core/types/node";
import { TemplateNodeTypes } from "@ssat/core/types/template/BaseNode/BaseNode";
import { TreeToText } from "@ssat/core/utils/treeToText";

type GenerateTemplateOptions = {
  /**
   * If true, validate the input CPG data before processing.
   * Defaults to true.
   */
  validateInput?: boolean;
  /**
   * If true, include text lines in the output.
   * Defaults to true.
   */
  includeTextLines?: boolean;
  /**
   * If true, include flattened graph in the output.
   * Defaults to false.
   */
  includeFlattened?: boolean;
};

type TemplateArtifacts = {
  templateTree: TreeNode[];
  templateResult: TemplateNodes[];
  textLines?: string[];
  flattened?: TemplateFlattenedGraph[];
};

class TemplateHandler {
  constructor() {
    // No external dependencies needed
  }

  // ---------- Validation helpers ----------

  private validateCPG(root: CPGRoot): void {
    try {
      validateCPGRoot([root.export]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new Error(`CPG validation failed: ${msg}`);
    }
  }

  // ---------- Template processing helpers ----------

  private buildTemplateArtifacts(root: CPGRoot, opts: GenerateTemplateOptions): TemplateArtifacts {
    const extractor = new TemplateExtractor();
    const converter = new TemplateConverter();
    const postProcessor = new PostProcessor();
    const planationTool = new PlanationTool([
      TemplateNodeTypes.VariableDeclaration,
      TemplateNodeTypes.ArrayDeclaration,
      TemplateNodeTypes.PointerDeclaration,
      TemplateNodeTypes.ParameterDeclaration,
      TemplateNodeTypes.AssignmentExpression,
      TemplateNodeTypes.FunctionDeclaration,
      TemplateNodeTypes.FunctionDefinition,
      TemplateNodeTypes.StandardLibCall,
      TemplateNodeTypes.UserDefinedCall,
      TemplateNodeTypes.CastExpression,
      TemplateNodeTypes.MemberAccess,
      TemplateNodeTypes.PointerDereference,
      TemplateNodeTypes.AddressOfExpression,
      TemplateNodeTypes.ArraySubscriptExpression,
      TemplateNodeTypes.BinaryExpression,
      TemplateNodeTypes.UnaryExpression,
      TemplateNodeTypes.SizeOfExpression,
      TemplateNodeTypes.Identifier,
      TemplateNodeTypes.Literal,
    ]);
    const treeToText = new TreeToText(["properties", "line_no", "code"]);

    const template: TreeNode[] = this.withContext("getTemplateTree", () => extractor.getTemplateTree(root.export));
    const converted = this.withContext("convertTree", () => converter.convertTree(template));
    let templateResult: TemplateNodes[] = this.withContext("removeInvalidNodes", () => postProcessor.removeInvalidNodes(converted));
    templateResult = this.withContext("addCodeProperties", () => postProcessor.addCodeProperties(templateResult, root));

    const result: TemplateArtifacts = {
      templateTree: template,
      templateResult,
    };

    if (opts.includeTextLines !== false) {
      const textLines = templateResult.map((rootNode) => treeToText.convert(rootNode));
      result.textLines = textLines;
    }

    if (opts.includeFlattened) {
      const flatten = planationTool.flatten(templateResult);

      // Validate flatten ids uniqueness
      this.validateFlattenIds(flatten[0]);

      result.flattened = flatten;
    }

    return result;
  }

  private validateFlattenIds(graph: TemplateFlattenedGraph): void {
    function collectIdsFromFlatten(graph: TemplateFlattenedGraph): number[] {
      const ids: number[] = [];
      for (const node of graph.nodes) {
        if (typeof node.id === "number") {
          ids.push(node.id);
        }
      }
      return ids;
    }

    const flattenIds = collectIdsFromFlatten(graph);
    const flattenUniqueIds = new Set(flattenIds);
    if (flattenIds.length !== flattenUniqueIds.size) {
      const duplicates = flattenIds.filter((id, idx) => flattenIds.indexOf(id) !== idx);
      throw new Error(`Duplicate node ids found in flattened template: ${[...new Set(duplicates)].join(", ")}`);
    }
  }

  private withContext<T>(fnName: string, fn: () => T): T {
    try {
      return fn();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new Error(`${fnName} failed: ${msg}`);
    }
  }

  // ---------- Public API ----------

  /**
   * Generate template artifacts from CPG data.
   *
   * Steps:
   * 1) Validate the input CPG data (optional)
   * 2) Extract template tree using TemplateExtractor
   * 3) Convert and process the template using TemplateConverter and PostProcessor
   * 4) Optionally generate text lines and flattened graph
   * 5) Return the processed template artifacts
   */
  async generateTemplate(cpgData: CPGRoot, opts: GenerateTemplateOptions = {}): Promise<TemplateArtifacts> {
    const { validateInput = true } = opts;

    // Validate input if requested
    if (validateInput) {
      this.validateCPG(cpgData);
    }

    // Build template artifacts
    return this.buildTemplateArtifacts(cpgData, opts);
  }

  /**
   * Generate template from a JSON string containing CPG data.
   */
  async generateTemplateFromString(cpgJsonString: string, opts: GenerateTemplateOptions = {}): Promise<TemplateArtifacts> {
    let cpgData: CPGRoot;
    try {
      cpgData = JSON.parse(cpgJsonString) as CPGRoot;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new Error(`Failed to parse CPG JSON: ${msg}`);
    }

    return this.generateTemplate(cpgData, opts);
  }
}

const templateHandler = new TemplateHandler();
export default templateHandler;
