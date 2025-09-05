import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface ITranslationUnit extends IBaseNode {
  nodeType: ASTNodeTypes.TranslationUnit;
}
