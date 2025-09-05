import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IPointerDeclaration extends IBaseNode {
  level: number;
  name: string;
  nodeType: ASTNodeTypes.PointerDeclaration;
  pointingType: string;
  storage?: string;
}
