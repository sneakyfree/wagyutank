"use client";
import Link from "next/link";
import { useAuth } from "../lib/auth";

export default function Header() {
  const { user, logout, loading } = useAuth();
  return (
    <header className="hdr">
      <div className="container hdr-inner">
        <Link href="/" className="logo">
          <span className="mark">W</span>
          <span>WagyuTank</span>
        </Link>
        <nav className="row hide-sm" style={{ gap: 20, marginLeft: 12 }}>
          <Link href="/browse" className="nav-link">Browse</Link>
          <Link href="/browse?product_type=semen" className="nav-link">Semen</Link>
          <Link href="/browse?product_type=embryo" className="nav-link">Embryos</Link>
          <Link href="/browse?product_type=clone_rights" className="nav-link">Cloning</Link>
          <Link href="/history" className="nav-link">Breed History</Link>
        </nav>
        <div className="spacer" />
        <Link href="/sell" className="btn btn-gold">+ Sell</Link>
        {loading ? null : user ? (
          <div className="row" style={{ gap: 10 }}>
            <Link href="/dashboard" className="nav-link hide-sm">
              {user.handle ? `@${user.handle}` : user.display_name}
            </Link>
            <button className="btn btn-ghost" onClick={logout}>Sign out</button>
          </div>
        ) : (
          <Link href="/login" className="btn btn-ghost">Sign in</Link>
        )}
      </div>
    </header>
  );
}
