import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IParameterList extends IBaseNode {
  nodeType: ASTNodeTypes.ParameterList;
}
