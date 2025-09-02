// vertex.ts
import { GraphSON, GraphSONValue, VertexProperty } from "./index";

export interface BindingVertexProperties {
  METHOD_FULL_NAME: VertexProperty<string[]>;
  NAME: VertexProperty<string[]>;
  SIGNATURE: VertexProperty<string[]>;
}

export interface BlockVertexProperties {
  ARGUMENT_INDEX: VertexProperty<GraphSONValue>;
  CODE: VertexProperty<string[]>;
  COLUMN_NUMBER: VertexProperty<GraphSONValue>;
  LINE_NUMBER: VertexProperty<GraphSONValue>;
  ORDER: VertexProperty<GraphSONValue>;
  TYPE_FULL_NAME: VertexProperty<string[]>;
}

export interface CallVertexProperties {
  ARGUMENT_INDEX: GraphSON<GraphSONValue>;
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  DISPATCH_TYPE: GraphSON<string[]>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  METHOD_FULL_NAME: GraphSON<string[]>;
  NAME: GraphSON<string[]>;
  ORDER: GraphSON<GraphSONValue>;
  SIGNATURE: GraphSON<string[]>;
  TYPE_FULL_NAME: GraphSON<string[]>;
}

export interface ControlStructureVertexProperties {
  ARGUMENT_INDEX: GraphSON<GraphSONValue>;
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  CONTROL_STRUCTURE_TYPE: GraphSON<string[]>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  ORDER: GraphSON<GraphSONValue>;
  PARSER_TYPE_NAME: GraphSON<string[]>;
}

export interface DependencyVertexProperties {
  DEPENDENCY_GROUP_ID: GraphSON<string[]>;
  NAME: GraphSON<string[]>;
  VERSION: GraphSON<string[]>;
}

export interface FieldIdentifierVertexProperties {
  ARGUMENT_INDEX: GraphSON<GraphSONValue>;
  CANONICAL_NAME: GraphSON<string[]>;
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  ORDER: GraphSON<GraphSONValue>;
}

export interface FileVertexProperties {
  CODE: GraphSON<string[]>;
  CONTENT: GraphSON<string[]>;
  NAME: GraphSON<string[]>;
  ORDER: GraphSON<GraphSONValue>;
}

export interface IdentifierVertexProperties {
  ARGUMENT_INDEX: GraphSON<GraphSONValue>;
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  NAME: GraphSON<string[]>;
  ORDER: GraphSON<GraphSONValue>;
  TYPE_FULL_NAME: GraphSON<string[]>;
}

export interface ImportVertexProperties {
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  IMPORTED_AS: GraphSON<string[]>;
  IMPORTED_ENTITY: GraphSON<string[]>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  ORDER: GraphSON<GraphSONValue>;
}

export interface JumpTargetVertexProperties {
  ARGUMENT_INDEX: GraphSON<GraphSONValue>;
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  NAME: GraphSON<string[]>;
  ORDER: GraphSON<GraphSONValue>;
  PARSER_TYPE_NAME: GraphSON<string[]>;
}

export interface LiteralVertexProperties {
  ARGUMENT_INDEX: GraphSON<GraphSONValue>;
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  ORDER: GraphSON<GraphSONValue>;
  TYPE_FULL_NAME: GraphSON<string[]>;
}

export interface LocalVertexProperties {
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  GENERIC_SIGNATURE: GraphSON<string[]>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  NAME: GraphSON<string[]>;
  ORDER: GraphSON<GraphSONValue>;
  TYPE_FULL_NAME: GraphSON<string[]>;
}

export interface MemberVertexProperties {
  AST_PARENT_FULL_NAME: GraphSON<string[]>;
  AST_PARENT_TYPE: GraphSON<string[]>;
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  GENERIC_SIGNATURE: GraphSON<string[]>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  NAME: GraphSON<string[]>;
  ORDER: GraphSON<GraphSONValue>;
  TYPE_FULL_NAME: GraphSON<string[]>;
}

export interface MetaDataVertexProperties {
  LANGUAGE: GraphSON<string[]>;
  OVERLAYS: GraphSON<string[]>;
  ROOT: GraphSON<string[]>;
  VERSION: GraphSON<string[]>;
}

export interface MethodParameterInVertexProperties {
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  EVALUATION_STRATEGY: GraphSON<string[]>;
  INDEX: GraphSON<GraphSONValue>;
  IS_VARIADIC: GraphSON<boolean[]>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  NAME: GraphSON<string[]>;
  ORDER: GraphSON<GraphSONValue>;
  TYPE_FULL_NAME: GraphSON<string[]>;
}

export type MethodParameterOutVertexProperties = MethodParameterInVertexProperties;

export interface MethodRefVertexProperties {
  ARGUMENT_INDEX: GraphSON<GraphSONValue>;
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  METHOD_FULL_NAME: GraphSON<string[]>;
  ORDER: GraphSON<GraphSONValue>;
  TYPE_FULL_NAME: GraphSON<string[]>;
}

export interface MethodReturnVertexProperties {
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  EVALUATION_STRATEGY: GraphSON<string[]>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  ORDER: GraphSON<GraphSONValue>;
  TYPE_FULL_NAME: GraphSON<string[]>;
}

export interface MethodVertexProperties {
  AST_PARENT_FULL_NAME: GraphSON<string[]>;
  AST_PARENT_TYPE: GraphSON<string[]>;
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  COLUMN_NUMBER_END: GraphSON<GraphSONValue>;
  FILENAME: GraphSON<string[]>;
  FULL_NAME: GraphSON<string[]>;
  GENERIC_SIGNATURE: GraphSON<string[]>;
  IS_EXTERNAL: GraphSON<boolean[]>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  LINE_NUMBER_END: GraphSON<GraphSONValue>;
  NAME: GraphSON<string[]>;
  ORDER: GraphSON<GraphSONValue>;
  SIGNATURE: GraphSON<string[]>;
}

export interface ModifierVertexProperties {
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  MODIFIER_TYPE: GraphSON<string[]>;
  ORDER: GraphSON<GraphSONValue>;
}

export interface NamespaceBlockVertexProperties {
  CODE: GraphSON<string[]>;
  FILENAME: GraphSON<string[]>;
  FULL_NAME: GraphSON<string[]>;
  NAME: GraphSON<string[]>;
  ORDER: GraphSON<GraphSONValue>;
}

export interface NamespaceVertexProperties {
  CODE: GraphSON<string[]>;
  NAME: GraphSON<string[]>;
  ORDER: GraphSON<GraphSONValue>;
}

export interface TypeDeclVertexProperties {
  ALIAS_TYPE_FULL_NAME?: GraphSON<string[]>;
  AST_PARENT_FULL_NAME: GraphSON<string[]>;
  AST_PARENT_TYPE: GraphSON<string[]>;
  CODE: GraphSON<string[]>;
  COLUMN_NUMBER: GraphSON<GraphSONValue>;
  FILENAME: GraphSON<string[]>;
  FULL_NAME: GraphSON<string[]>;
  GENERIC_SIGNATURE: GraphSON<string[]>;
  IS_EXTERNAL: GraphSON<boolean[]>;
  LINE_NUMBER: GraphSON<GraphSONValue>;
  NAME: GraphSON<string[]>;
  ORDER: GraphSON<GraphSONValue>;
}

export interface TypeVertexProperties {
  FULL_NAME: GraphSON<string[]>;
  NAME: GraphSON<string[]>;
  TYPE_DECL_FULL_NAME: GraphSON<string[]>;
}

export interface VertexByLabelMap {
  BINDING: BindingVertexProperties;
  BLOCK: BlockVertexProperties;
  CALL: CallVertexProperties;
  CONTROL_STRUCTURE: ControlStructureVertexProperties;
  DEPENDENCY: DependencyVertexProperties;
  FIELD_IDENTIFIER: FieldIdentifierVertexProperties;
  FILE: FileVertexProperties;
  IDENTIFIER: IdentifierVertexProperties;
  IMPORT: ImportVertexProperties;
  JUMP_TARGET: JumpTargetVertexProperties;
  LITERAL: LiteralVertexProperties;
  LOCAL: LocalVertexProperties;
  MEMBER: MemberVertexProperties;
  META_DATA: MetaDataVertexProperties;
  METHOD: MethodVertexProperties;
  METHOD_PARAMETER_IN: MethodParameterInVertexProperties;
  METHOD_PARAMETER_OUT: MethodParameterOutVertexProperties;
  METHOD_REF: MethodRefVertexProperties;
  METHOD_RETURN: MethodReturnVertexProperties;
  MODIFIER: ModifierVertexProperties;
  NAMESPACE: NamespaceVertexProperties;
  NAMESPACE_BLOCK: NamespaceBlockVertexProperties;
  TYPE: TypeVertexProperties;
  TYPE_DECL: TypeDeclVertexProperties;
}

/**
 * A generic vertex wrapper with its label and properties.
 */
export interface VertexGeneric<L extends keyof VertexByLabelMap = keyof VertexByLabelMap> {
  "@type": string;
  id: {
    "@type": string;
    "@value": number;
  };
  label: L;
  properties: VertexByLabelMap[L];
}
