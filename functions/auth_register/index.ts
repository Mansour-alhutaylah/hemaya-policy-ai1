import "dotenv/config";
import bcrypt from "bcrypt";
import { dbQuery } from "../_shared/db";

export default async function handler(req: any, res: any) {
  try {
    if (req.method !== "POST") return res.status(405).json({ error: "Method not allowed" });

    const { first_name, last_name, phone, email, password } = req.body || {};
    if (!first_name || !last_name || !phone || !email || !password)
      return res.status(400).json({ error: "Missing fields" });

    const hash = await bcrypt.hash(password, 10);

    const r = await dbQuery(
      `INSERT INTO users (first_name,last_name,phone,email,role,password_hash)
       VALUES ($1,$2,$3,$4,'user',$5)
       RETURNING id, first_name, last_name, email, phone, role`,
      [first_name, last_name, phone, email.toLowerCase(), hash]
    );

    res.json({ ok: true, user: r.rows[0] });
  } catch (e: any) {
    // unique violation
    if (e?.code === "23505") return res.status(409).json({ error: "Email/Phone already exists" });
    res.status(500).json({ error: e.message });
  }
}
