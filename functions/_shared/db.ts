import { Pool } from "pg";

const connectionString = process.env.DATABASE_URL;
if (!connectionString) throw new Error("DATABASE_URL is not set");

export const pool = new Pool({ connectionString });

export async function dbQuery<T = any>(text: string, params?: any[]) {
  return pool.query<T>(text, params);
}
