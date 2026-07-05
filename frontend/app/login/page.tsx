"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "../../lib/auth";

function LoginInner() {
  const { login } = useAuth();
  const router = useRouter();
  const next = useSearchParams().get("next") || "/dashboard";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    try { await login(email, password); router.push(next); }
    catch (e: any) { setErr(e.message); }
  }

  return (
    <div className="container section" style={{ maxWidth: 420 }}>
      <h1>Sign in</h1>
      <form onSubmit={submit} className="stack" style={{ marginTop: 16 }}>
        <div className="field"><label>Email</label><input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
        <div className="field"><label>Password</label><input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
        {err && <p className="help" style={{ color: "var(--red)" }}>{err}</p>}
        <button className="btn btn-gold btn-block btn-lg" type="submit">Sign in</button>
      </form>
      <p className="muted center" style={{ marginTop: 16 }}>
        New here? <Link href="/register" className="gold">Create an account</Link>
      </p>
    </div>
  );
}

export default function Login() {
  return <Suspense fallback={<div className="container section">Loading…</div>}><LoginInner /></Suspense>;
}
