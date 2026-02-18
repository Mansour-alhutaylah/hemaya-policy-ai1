import { dbQuery } from "../_shared/db";

export default async function handler(req: any, res: any) {
  try {
    const result = await dbQuery(
      `SELECT id, name, type, framework_code, status, uploaded_at
       FROM policies
       ORDER BY uploaded_at DESC
       LIMIT 50`
    );

    res.json({ ok: true, items: result.rows });
  } catch (e: any) {
    res.status(500).json({ ok: false, error: e.message });
  }
}
