import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IParameterList extends IBaseNode {
  nodeType: TemplateNodeTypes.ParameterList;
}
