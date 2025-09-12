import { IBaseNode, TemplateNodeTypes } from "./BaseNode/BaseTypes";

export interface IBreakStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.BreakStatement;
}

export interface ICaseLabel extends IBaseNode {
  nodeType: TemplateNodeTypes.CaseLabel;
}

export interface IContinueStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.ContinueStatement;
}

export interface IDefaultLabel extends IBaseNode {
  nodeType: TemplateNodeTypes.DefaultLabel;
}

export interface IDoWhileStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.DoWhileStatement;
}

export interface IForStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.ForStatement;
}

export interface IGotoStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.GotoStatement;
  jumpTarget: string;
}

export interface IIfStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.IfStatement;
}

export interface ILabel extends IBaseNode {
  nodeType: TemplateNodeTypes.Label;
  name: string;
}

export interface IReturnStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.ReturnStatement;
}

export interface ISwitchStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.SwitchStatement;
}

export interface IWhileStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.WhileStatement;
}
