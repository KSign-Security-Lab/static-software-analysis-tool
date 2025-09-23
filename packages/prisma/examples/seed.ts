#!/usr/bin/env tsx

/**
 * Database seed script for populating the database with sample data from a folder
 */

import {
  DatabaseService,
  uploadGraphsFromDirectory,
  type GraphData,
} from '@ssat/prisma';
import fs from 'node:fs/promises';
import path from 'node:path';

// Hardcoded folder path - change this to your data folder
const DATA_FOLDER = '/home/devel03/static-software-analysis-tool/data';

/**
 * Recursively find all JSON files in a directory
 */
async function findJsonFilesRecursively(
  dirPath: string,
  extensions: string[] = ['.json']
): Promise<string[]> {
  const files: string[] = [];

  try {
    const entries = await fs.readdir(dirPath, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(dirPath, entry.name);

      if (entry.isDirectory()) {
        // Recursively scan subdirectories
        const subFiles = await findJsonFilesRecursively(fullPath, extensions);
        files.push(...subFiles);
      } else if (entry.isFile()) {
        // Check if file has one of the target extensions
        const ext = path.extname(entry.name).toLowerCase();
        if (extensions.includes(ext)) {
          files.push(fullPath);
        }
      }
    }
  } catch (error) {
    // Directory doesn't exist or can't be read
    console.log(`⚠️  Directory not accessible: ${dirPath}`);
  }

  return files;
}

/**
 * Transform raw AST tree data to IASTResult format
 */
function transformRawASTToIASTResult(rawData: any, filePath: string): any {
  // Extract filename from path
  const fileName = path.basename(filePath, '.json');

  // If rawData is an array, take the first element (root node)
  const rootNode = Array.isArray(rawData) ? rawData[0] : rawData;

  // Extract nodes and edges from the raw AST tree
  const nodes: any[] = [];
  const edges_ast_pc: any[] = [];
  const edges_ast_sb: any[] = [];
  const edges_ast_guard: any[] = [];
  let nodeIdCounter = 1;

  // Recursively extract nodes and edges
  function extractNodesAndEdges(node: any, parentId?: number) {
    if (!node || typeof node !== 'object') return;

    // Add current node
    const nodeId = node.id || nodeIdCounter++;
    nodes.push({
      sid: nodeId,
      node_type: node.nodeType || 'Unknown',
      code: node.code || '',
      orig_id: nodeId,
      feat: {
        node_type_id: 1,
        train_mask: 1,
        in_loop: 0,
        is_loop: 0,
        ctx_guard_strength: 0,
        ctx_upper_bound_norm: 0,
        is_buffer_decl: 0,
        buffer_size_state: 0,
        buffer_size_norm: 0,
        call_sem_cat_id: 0,
        call_flag_danger_unbounded: 0,
        call_flag_len_linked_to_dst: 0,
        call_flag_sizeof_non_dst: 0,
        call_flag_has_varargs: 0,
        call_dst_is_field: 0,
        call_size_kind: 0,
        call_len_linked_to_dst_extended: 0,
        call_size_is_sizeof_base_struct: 0,
        call_size_mismatch_field: 0,
        alloc_sizeof_state: 0,
      },
    });

    // Add edge from parent if exists
    if (parentId !== undefined) {
      edges_ast_pc.push({
        src: parentId,
        dst: nodeId,
        edge_type: 1,
      });
    }

    // Process children
    if (node.children && Array.isArray(node.children)) {
      node.children.forEach((child: any) => {
        extractNodesAndEdges(child, nodeId);
      });
    }
  }

  extractNodesAndEdges(rootNode);

  return {
    file: filePath, // Use full path to make it unique
    label: 1,
    ast_result: {
      nodes,
      edges_ast_pc,
      edges_ast_sb,
      edges_ast_guard,
    },
  };
}

/**
 * Upload graphs from a directory recursively
 */
async function uploadGraphsRecursively(
  directoryPath: string,
  graphType: GraphData['type'],
  options: {
    versionTag?: string;
    overwrite?: boolean;
  },
  db: DatabaseService
) {
  const jsonFiles = await findJsonFilesRecursively(directoryPath);

  if (jsonFiles.length === 0) {
    console.log(`   No JSON files found in ${directoryPath}`);
    return {
      successful: 0,
      failed: 0,
      errors: [],
      results: [],
    };
  }

  console.log(`   Found ${jsonFiles.length} JSON files`);

  const results: any[] = [];
  const errors: Array<{ file: string; error: string }> = [];
  let successful = 0;
  let failed = 0;

  for (const filePath of jsonFiles) {
    try {
      const fileContent = await fs.readFile(filePath, 'utf-8');
      const rawData = JSON.parse(fileContent);

      // Transform raw data to expected format based on graph type
      let transformedData: any;
      switch (graphType) {
        case 'AST':
          // Transform raw AST tree to IASTResult format
          transformedData = transformRawASTToIASTResult(rawData, filePath);
          break;
        case 'DFG':
          // DFG data should already be in correct format
          transformedData = rawData;
          break;
        case 'CPG':
          // CPG data should already be in correct format
          transformedData = rawData;
          break;
        case 'TEMPLATE':
          // Template data should already be in correct format
          transformedData = rawData;
          break;
        default:
          throw new Error(`Unsupported graph type: ${graphType}`);
      }

      // Create the graph data object based on type
      let data: GraphData;
      switch (graphType) {
        case 'AST':
          data = { type: 'AST', data: transformedData };
          break;
        case 'DFG':
          data = { type: 'DFG', data: transformedData };
          break;
        case 'CPG':
          data = { type: 'CPG', data: transformedData };
          break;
        case 'TEMPLATE':
          data = { type: 'TEMPLATE', data: transformedData };
          break;
        default:
          throw new Error(`Unsupported graph type: ${graphType}`);
      }

      // Upload the graph using the appropriate method
      // Use a unique version tag for each file to avoid conflicts
      const uniqueVersionTag = `${options.versionTag}-${path.basename(filePath, '.json')}`;

      let result;
      switch (graphType) {
        case 'AST':
          result = await db.uploadASTGraph(
            data.data as any,
            filePath,
            uniqueVersionTag,
            {},
            undefined
          );
          break;
        case 'DFG':
          result = await db.uploadDFGGraph(
            data.data as any,
            filePath,
            uniqueVersionTag,
            {}
          );
          break;
        case 'CPG':
          result = await db.uploadCPGGraph(
            data.data as any,
            filePath,
            uniqueVersionTag,
            {}
          );
          break;
        case 'TEMPLATE':
          result = await db.uploadTemplateGraph(
            data.data as any,
            filePath,
            uniqueVersionTag,
            {}
          );
          break;
        default:
          throw new Error(`Unsupported graph type: ${graphType}`);
      }

      results.push({
        graph: result,
        nodeCount: 0, // Will be calculated by the service
        edgeCount: 0,
        isNew: true,
      });

      successful++;
      console.log(`   ✅ ${path.basename(filePath)}`);
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      errors.push({
        file: filePath,
        error: errorMessage,
      });
      failed++;
      console.log(`   ❌ ${path.basename(filePath)}: ${errorMessage}`);
    }
  }

  return {
    successful,
    failed,
    errors,
    results,
  };
}

async function seedDatabase() {
  console.log('🌱 Starting database seed from folder...');
  console.log(`📁 Reading from folder: ${DATA_FOLDER}`);

  const db = new DatabaseService();

  try {
    await db.connect();
    console.log('✅ Connected to database');

    // Check if data folder exists
    try {
      await fs.access(DATA_FOLDER);
    } catch (error) {
      console.error(`❌ Data folder not found: ${DATA_FOLDER}`);
      console.log(
        '💡 Please create the data folder and add your JSON graph files.'
      );
      console.log('   Expected structure (supports nested directories):');
      console.log('   data/');
      console.log('   ├── ast/     (AST graph JSON files)');
      console.log('   │   ├── file1.json');
      console.log('   │   └── subfolder/');
      console.log('   │       └── file2.json');
      console.log('   ├── dfg/     (DFG graph JSON files)');
      console.log('   ├── cpg/     (CPG graph JSON files)');
      console.log('   └── template/ (Template graph JSON files)');
      process.exit(1);
    }

    // Check if we already have data
    const existingGraphs = await db.prisma.graph.count();
    if (existingGraphs > 0) {
      console.log(`⚠️  Database already contains ${existingGraphs} graphs.`);
      console.log('🔄 Continuing with recursive seed (will add new graphs)...');
    }

    let totalUploaded = 0;
    let totalErrors = 0;

    // Define graph types and their corresponding folders
    const graphTypes = [
      { type: 'AST' as const, folder: 'ast' },
      { type: 'DFG' as const, folder: 'dfg' },
      { type: 'CPG' as const, folder: 'cpg' },
      { type: 'TEMPLATE' as const, folder: 'template' },
    ];

    // Process each graph type recursively
    for (const { type, folder } of graphTypes) {
      const folderPath = path.join(DATA_FOLDER, folder);

      try {
        await fs.access(folderPath);
        console.log(
          `📊 Processing ${type} graphs from ${folder}/ (recursive)...`
        );

        const result = await uploadGraphsRecursively(
          folderPath,
          type,
          {
            versionTag: 'v1.0.0',
            overwrite: false,
          },
          db
        );

        console.log(
          `✅ ${type}: ${result.successful} graphs uploaded successfully`
        );
        if (result.failed > 0) {
          console.log(`❌ ${type}: ${result.failed} graphs failed to upload`);
          result.errors.forEach((error) => {
            console.log(`   • ${path.basename(error.file)}: ${error.error}`);
          });
        }

        totalUploaded += result.successful;
        totalErrors += result.failed;
      } catch (error) {
        if (error instanceof Error && error.message.includes('ENOENT')) {
          console.log(`⚠️  ${type} folder not found: ${folderPath} (skipping)`);
        } else {
          console.error(`❌ Error processing ${type} folder:`, error);
          totalErrors++;
        }
      }
    }

    console.log(`\n✅ Database seeding complete!`);
    console.log(
      `📈 Summary: ${totalUploaded} graphs uploaded, ${totalErrors} errors`
    );

    // Display final statistics
    const graphs = await db.prisma.graph.findMany();
    const astNodes = await db.prisma.aSTNode.count();
    const astEdges = await db.prisma.aSTEdge.count();
    const dfgNodes = await db.prisma.dFGNode.count();
    const dfgEdges = await db.prisma.dFGEdge.count();

    console.log('\n📊 Database Statistics:');
    console.log(`Total graphs: ${graphs.length}`);
    console.log(`- AST: ${astNodes} nodes, ${astEdges} edges`);
    console.log(`- DFG: ${dfgNodes} nodes, ${dfgEdges} edges`);
    console.log(`- Total nodes: ${astNodes + dfgNodes}`);
    console.log(`- Total edges: ${astEdges + dfgEdges}`);
  } catch (error) {
    console.error('❌ Error seeding database:', error);
    process.exit(1);
  } finally {
    await db.disconnect();
  }
}

// Run the seed function
// Uncomment the following lines to run the script directly
if (import.meta.url === `file://${process.argv[1]}`) {
  seedDatabase().catch(console.error);
}

export { seedDatabase };
