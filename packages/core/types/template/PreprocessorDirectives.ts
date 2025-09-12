import { IBaseNode, TemplateNodeTypes } from "./BaseNode/BaseTypes";

export interface IIncludeDirective extends IBaseNode {
  nodeType: TemplateNodeTypes.IncludeDirective;
  name: string;
}

export interface IMacroDefinition extends IBaseNode {
  nodeType: TemplateNodeTypes.MacroDefinition;
}
