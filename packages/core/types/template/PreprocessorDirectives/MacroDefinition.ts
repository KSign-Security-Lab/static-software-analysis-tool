import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IMacroDefinition extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.MacroDefinition;
  value: string;
}
