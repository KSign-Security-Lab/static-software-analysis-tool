import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface ITranslationUnit extends IBaseNode {
  nodeType: TemplateNodeTypes.TranslationUnit;
}
