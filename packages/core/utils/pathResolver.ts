/**
 * Robust Path Resolution Utility
 *
 * This utility provides consistent path resolution across the entire codebase,
 * regardless of the current working directory or module location.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Get the absolute path to the repository root
 * This works regardless of where the script is executed from
 */
export function getRepoRoot(): string {
  // Get the directory of the current file (this utility)
  const currentFileDir = path.dirname(fileURLToPath(import.meta.url));

  // Navigate up to the repo root from packages/core/utils/
  // packages/core/utils -> packages/core -> packages -> repo root
  return path.resolve(currentFileDir, "../../..");
}

/**
 * Get the absolute path to the packages directory
 */
export function getPackagesDir(): string {
  return path.join(getRepoRoot(), "packages");
}

/**
 * Get the absolute path to the core package directory
 */
export function getCoreDir(): string {
  return path.join(getPackagesDir(), "core");
}

/**
 * Get the absolute path to the agent package directory
 */
export function getAgentDir(): string {
  return path.join(getPackagesDir(), "agent");
}

/**
 * Get the absolute path to the CLI package directory
 */
export function getCliDir(): string {
  return path.join(getPackagesDir(), "cli");
}

/**
 * Resolve a path relative to the repository root
 */
export function resolveFromRepoRoot(relativePath: string): string {
  return path.resolve(getRepoRoot(), relativePath);
}

/**
 * Resolve a path relative to the packages directory
 */
export function resolveFromPackages(relativePath: string): string {
  return path.resolve(getPackagesDir(), relativePath);
}

/**
 * Resolve a path relative to the core package
 */
export function resolveFromCore(relativePath: string): string {
  return path.resolve(getCoreDir(), relativePath);
}

/**
 * Resolve a path relative to the agent package
 */
export function resolveFromAgent(relativePath: string): string {
  return path.resolve(getAgentDir(), relativePath);
}

/**
 * Resolve a path relative to the CLI package
 */
export function resolveFromCli(relativePath: string): string {
  return path.resolve(getCliDir(), relativePath);
}

/**
 * Predefined paths for commonly used files
 */
export const PATHS = {
  // Core package paths
  AST_EXTRACTOR: resolveFromCore("ast/ASTExtractor.py"),
  DFG_EXTRACTOR: resolveFromCore("dfg/python/DFGExtractor.py"),

  // Data directories
  DATA_DIR: resolveFromRepoRoot("data"),
  TEMP_DIR: resolveFromRepoRoot("data/temp"),

  // Template directories
  TEMPLATE_DIR: resolveFromRepoRoot("data/temp/template"),
  CPG_DIR: resolveFromRepoRoot("data/temp/cpg"),
  AST_DIR: resolveFromRepoRoot("data/temp/ast"),
  DFG_DIR: resolveFromRepoRoot("data/temp/dfg"),
} as const;

/**
 * Validate that a file exists at the given path
 */
export async function validatePath(filePath: string, description = "file"): Promise<string> {
  const fs = await import("node:fs");
  if (!fs.existsSync(filePath)) {
    throw new Error(`${description} not found at: ${filePath}`);
  }
  return filePath;
}

/**
 * Get a validated path for a commonly used file (async version)
 */
export async function getValidatedPath(key: keyof typeof PATHS): Promise<string> {
  return await validatePath(PATHS[key], key.replace(/_/g, " ").toLowerCase());
}

/**
 * Get a path without validation (synchronous version)
 * Use this for constants and when you're sure the path exists
 */
export function getPath(key: keyof typeof PATHS): string {
  return PATHS[key];
}

/**
 * Debug function to print all resolved paths
 */
export async function debugPaths(): Promise<void> {
  const fs = await import("node:fs");
  console.log("=== Path Resolution Debug ===");
  console.log("Repo Root:", getRepoRoot());
  console.log("Packages Dir:", getPackagesDir());
  console.log("Core Dir:", getCoreDir());
  console.log("Agent Dir:", getAgentDir());
  console.log("CLI Dir:", getCliDir());
  console.log("\n=== Predefined Paths ===");
  for (const [key, value] of Object.entries(PATHS)) {
    const exists = fs.existsSync(value);
    console.log(`${key}: ${value} ${exists ? "✓" : "✗"}`);
  }
}
