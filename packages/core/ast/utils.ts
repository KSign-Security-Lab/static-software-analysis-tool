import { TemplateNodes } from "../types/node";
import { TemplateNodeTypes } from "../types/template/BaseNode/BaseTypes";

const INVALID_FUNCTION_NAMES = ["", "<clinit>", "<empty>"];

export function recursivelyGetFunctionsFromTemplate(template: TemplateNodes[]): TemplateNodes[] {
  return template
    .flatMap((node) => {
      const functions: TemplateNodes[] = [];
      functions.push(node);
      if (Array.isArray(node.children)) {
        functions.push(...recursivelyGetFunctionsFromTemplate(node.children));
      }
      return functions;
    })
    .filter((node) => node.nodeType === TemplateNodeTypes.FunctionDefinition)
    .filter((node) => !INVALID_FUNCTION_NAMES.includes(node.name ?? ""))
    .filter((node) => Array.isArray(node.children) && node.children.length > 0)
    .filter((node) => /bad|good|sink/i.test(node.name ?? ""));
}
