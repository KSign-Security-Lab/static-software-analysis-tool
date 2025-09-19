#!/usr/bin/env tsx

/**
 * Example usage of the database service for uploading graph data
 */

import {
  DatabaseService,
  uploadGraph,
  uploadGraphFromFile,
  uploadGraphsFromDirectory,
  GraphType,
} from '@ssat/prisma';

async function exampleUsage() {
  console.log('🚀 Database Service Example Usage\n');

  // Example 1: Upload AST graph data
  console.log('1. Uploading AST graph data...');
  try {
    const astGraph = {
      type: 'AST' as const,
      data: {
        file: 'example.c',
        label: 1,
        ast_result: {
          nodes: [
            {
              sid: 1,
              node_type: 'FunctionDeclaration',
              code: 'int main() { return 0; }',
              orig_id: 1,
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
            },
          ],
          edges_ast_pc: [],
          edges_ast_sb: [],
          edges_ast_guard: [],
        },
      },
    };

    const result = await uploadGraph(astGraph, {
      sourceFile: 'example.c',
      sourceLabel: '1',
      versionTag: 'v1.0.0',
    });

    console.log(
      `✅ AST graph uploaded: ${result.graph.id} (${result.nodeCount} nodes, ${result.edgeCount} edges)`
    );
  } catch (error) {
    console.error('❌ Error uploading AST graph:', error);
  }

  // Example 2: Upload DFG graph data
  console.log('\n2. Uploading DFG graph data...');
  try {
    const dfgGraph = {
      type: 'DFG' as const,
      data: {
        nodes: [
          {
            id: 1,
            features: {
              nodeType: 'VARIABLE_DECLARATION',
              inDegreeDFG: 0,
              outDegreeDFG: 1,
              defCount: 1,
              useCount: 0,
              isBufferAccess: false,
              isSinkAssignment: false,
              isSinkCallUnbounded: false,
              isSinkCallBounded: false,
              callDestinationIndexed: false,
              callLengthLinkedToDestination: false,
              callSizeNonConstant: false,
              callDangerUnbounded: false,
            },
          },
        ],
        edges: [],
      },
    };

    const result = await uploadGraph(dfgGraph, {
      sourceFile: 'example.c',
      versionTag: 'v1.0.0',
    });

    console.log(
      `✅ DFG graph uploaded: ${result.graph.id} (${result.nodeCount} nodes, ${result.edgeCount} edges)`
    );
  } catch (error) {
    console.error('❌ Error uploading DFG graph:', error);
  }

  // Example 3: Query graphs
  console.log('\n3. Querying graphs...');
  try {
    const db = new DatabaseService();
    await db.connect();

    const graphs = await db.getGraphsByTypeAndFile(GraphType.AST, 'example.c');
    console.log(`Found ${graphs.length} AST graphs for example.c`);

    if (graphs.length > 0) {
      const graph = graphs[0];
      console.log(`Graph ID: ${graph.id}`);
      console.log(`Nodes: ${graph.nodes.length}`);
      console.log(`Edges: ${graph.edges.length}`);
    }

    await db.disconnect();
  } catch (error) {
    console.error('❌ Error querying graphs:', error);
  }

  // Example 4: Upload from file (if file exists)
  console.log('\n4. Uploading from file...');
  try {
    // Note: File upload is not implemented in this example
    console.log('File upload functionality not implemented in this example');
  } catch (error) {
    console.error('❌ Error uploading from file:', error);
  }

  console.log('\n✨ Example usage completed!');
}

// Run the example
// Note: In a real implementation, you would check if this is the main module
// if (require.main === module) {
//   exampleUsage().catch(console.error);
// }

export { exampleUsage };
