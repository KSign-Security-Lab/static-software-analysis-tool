import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface ISwitchStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.SwitchStatement;
}
