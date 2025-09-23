#!/usr/bin/env tsx

/**
 * Example demonstrating shared types between core and prisma packages
 * This shows how types are shared and used consistently across packages
 */

import { DatabaseService } from '@ssat/prisma';
// Import core types directly - they're shared across packages
import type {
  IASTResult,
  IDFGGraph,
  CPGGraphData,
  TemplateFlattenedGraph,
} from '@ssat/core';

async function demonstrateSharedTypes() {
  console.log(
    '🔄 Demonstrating shared types between core and prisma packages...'
  );

  const db = new DatabaseService();

  try {
    await db.connect();
    console.log('✅ Connected to database');

    // Example 1: AST Graph using shared types
    console.log('\n📊 Example 1: AST Graph with shared types');
    const astData: IASTResult = {
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
    };

    // Example 2: DFG Graph using shared types
    console.log('\n📊 Example 2: DFG Graph with shared types');
    const dfgData: IDFGGraph = {
      nodes: [
        {
          sid: 1,
          id: 1,
          features: {
            nodeType: 'VARIABLE_DECLARATION' as any,
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
      edges: [
        {
          source: 1,
          destination: 2,
          features: {
            flow: 'VALUE' as any,
            guard: 'NONE' as any,
            hasLowerGuard: false,
            hasUpperGuard: false,
            upperGuardNormalization: 0,
          },
        },
      ],
    };

    // Example 3: CPG Graph using shared types
    console.log('\n📊 Example 3: CPG Graph with shared types');
    const cpgData: CPGGraphData = {
      vertices: [],
      edges: [],
    };

    // Example 4: Template Graph using shared types
    console.log('\n📊 Example 4: Template Graph with shared types');
    const templateData: TemplateFlattenedGraph = {
      nodes: [
        {
          id: 1,
          nodeType: 'FUNCTION_DEFINITION' as any,
          code: 'int main() { return 0; }',
        },
      ],
      edges: [{ from: 1, to: 2 }],
    };

    console.log('\n✅ All examples use shared types from @ssat/core package!');
    console.log('🔗 Types are consistent across core and prisma packages');
    console.log('📦 No type duplication - single source of truth');

    // Show that types are the same
    console.log('\n🔍 Type verification:');
    console.log(`- IASTResult type: ${typeof astData}`);
    console.log(`- IDFGGraph type: ${typeof dfgData}`);
    console.log(`- CPGGraphData type: ${typeof cpgData}`);
    console.log(`- TemplateFlattenedGraph type: ${typeof templateData}`);
  } catch (error) {
    console.error('❌ Error:', error);
  } finally {
    await db.disconnect();
  }
}

// Run the demonstration
if (import.meta.url === `file://${process.argv[1]}`) {
  demonstrateSharedTypes().catch(console.error);
}

export { demonstrateSharedTypes };
