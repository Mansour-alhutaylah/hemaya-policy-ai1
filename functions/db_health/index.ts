import { dbQuery } from "../_shared/db";

export default async function handler(req: any, res: any) {
  try {
    const r = await dbQuery("SELECT now() as server_time");
    res.json({ ok: true, time: r.rows[0].server_time });
  } catch (e: any) {
    res.status(500).json({ ok: false, error: e.message });
  }
}
