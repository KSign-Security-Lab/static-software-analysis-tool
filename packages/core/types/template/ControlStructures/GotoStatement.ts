import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IGotoStatement extends IBaseNode {
  jumpTarget: string;
  nodeType: TemplateNodeTypes.GotoStatement;
}
