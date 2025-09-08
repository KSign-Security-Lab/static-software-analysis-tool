import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IIncludeDirective extends IBaseNode {
  name: string; // The name of the included file, e.g., "stdio.h"
  nodeType: TemplateNodeTypes.IncludeDirective;
}
