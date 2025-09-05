import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface ILiteral extends IBaseNode {
  nodeType: ASTNodeTypes.Literal;
  size?: number;
  type: string;
  value: boolean | null | number | string;
}
