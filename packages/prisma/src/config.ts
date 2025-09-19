/**
 * Database configuration and environment variables
 */

export interface DatabaseConfig {
  url: string;
  poolSize?: number;
  connectionTimeout?: number;
  queryTimeout?: number;
  logQueries?: boolean;
}

/**
 * Get database configuration from environment variables
 */
export function getDatabaseConfig(): DatabaseConfig {
  const url = process.env.DATABASE_URL;

  if (!url) {
    throw new Error('DATABASE_URL environment variable is required');
  }

  return {
    url,
    poolSize: process.env.DATABASE_POOL_SIZE
      ? parseInt(process.env.DATABASE_POOL_SIZE)
      : 10,
    connectionTimeout: process.env.DATABASE_CONNECTION_TIMEOUT
      ? parseInt(process.env.DATABASE_CONNECTION_TIMEOUT)
      : 10000,
    queryTimeout: process.env.DATABASE_QUERY_TIMEOUT
      ? parseInt(process.env.DATABASE_QUERY_TIMEOUT)
      : 30000,
    logQueries: process.env.DATABASE_LOG_QUERIES === 'true',
  };
}

/**
 * Validate database configuration
 */
export function validateDatabaseConfig(config: DatabaseConfig): {
  valid: boolean;
  errors: string[];
} {
  const errors: string[] = [];

  if (!config.url) {
    errors.push('Database URL is required');
  } else if (!config.url.startsWith('postgresql://')) {
    errors.push('Database URL must be a PostgreSQL connection string');
  }

  if (config.poolSize && (config.poolSize < 1 || config.poolSize > 100)) {
    errors.push('Pool size must be between 1 and 100');
  }

  if (
    config.connectionTimeout &&
    (config.connectionTimeout < 1000 || config.connectionTimeout > 60000)
  ) {
    errors.push(
      'Connection timeout must be between 1000 and 60000 milliseconds'
    );
  }

  if (
    config.queryTimeout &&
    (config.queryTimeout < 1000 || config.queryTimeout > 300000)
  ) {
    errors.push('Query timeout must be between 1000 and 300000 milliseconds');
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

/**
 * Default database configuration
 */
export const DEFAULT_DATABASE_CONFIG: DatabaseConfig = {
  url:
    process.env.DATABASE_URL ||
    'postgresql://username:password@localhost:5432/ssat_db?schema=public',
  poolSize: 10,
  connectionTimeout: 10000,
  queryTimeout: 30000,
  logQueries: false,
};
