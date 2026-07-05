"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../../lib/auth";

export default function Register() {
  const { register } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ display_name: "", email: "", password: "", handle: "" });
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    try {
      await register({ ...form, handle: form.handle || undefined });
      router.push("/dashboard");
    } catch (e: any) { setErr(e.message); }
  }

  return (
    <div className="container section" style={{ maxWidth: 460 }}>
      <h1>Create your account</h1>
      <p className="muted">One account to buy and sell. Free.</p>
      <form onSubmit={submit} className="stack" style={{ marginTop: 16 }}>
        <div className="field"><label>Ranch / display name</label><input className="input" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} required /></div>
        <div className="field"><label>Storefront handle (optional)</label>
          <div className="row" style={{ gap: 4 }}><span className="faint">wagyutank.com/u/</span>
            <input className="input" value={form.handle} onChange={(e) => setForm({ ...form, handle: e.target.value.toLowerCase() })} placeholder="rockingw" /></div>
        </div>
        <div className="field"><label>Email</label><input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></div>
        <div className="field"><label>Password</label><input className="input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={8} /></div>
        {err && <p className="help" style={{ color: "var(--red)" }}>{err}</p>}
        <button className="btn btn-gold btn-block btn-lg" type="submit">Create account</button>
      </form>
      <p className="muted center" style={{ marginTop: 16 }}>
        Already have an account? <Link href="/login" className="gold">Sign in</Link>
      </p>
    </div>
  );
}
