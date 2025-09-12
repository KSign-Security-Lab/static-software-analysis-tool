// ============================================================================
// TEMPLATE TYPES INDEX
// ============================================================================
// This file provides clean, consolidated imports for all template types

// Re-export commonly used types for convenience
export type { IBaseNode, TemplateFlattenedNode, TemplateNodes, TemplateNodeTypes } from "../node";
// Base types and utilities
export * from "./BaseNode/BaseTypes";

export * from "./BaseNode/UtilityTypes";
// Consolidated type groups
export * from "./Blocks";
export * from "./ControlStructures";
export * from "./DataTypes";
export * from "./Expressions";
export * from "./PreprocessorDirectives";

export * from "./ProgramStructures";
