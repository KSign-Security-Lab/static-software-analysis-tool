import { TemplateNodes } from "../types/node";
import { TemplateNodeTypes } from "../types/template/BaseNode/BaseTypes";

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
    .filter((node) => node.nodeType === TemplateNodeTypes.FunctionDeclaration || node.nodeType === TemplateNodeTypes.FunctionDefinition);
}
