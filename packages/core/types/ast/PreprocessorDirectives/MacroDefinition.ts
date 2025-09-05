import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IMacroDefinition extends IBaseNode {
  name: string;
  nodeType: ASTNodeTypes.MacroDefinition;
  value: string;
}
