"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "../lib/api";
import ListingCard from "../components/ListingCard";

export default function Home() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [listings, setListings] = useState<any[]>([]);
  const [foundation, setFoundation] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.browse({ limit: 8 }), api.foundation()])
      .then(([ls, fs]) => { setListings(ls); setFoundation(fs.slice(0, 6)); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <section className="hero">
        <div className="container">
          <h1>The world's marketplace for frozen Wagyu genetics.</h1>
          <p className="sub" style={{ marginTop: 14 }}>
            Semen, embryos, and cloning rights — from foundation bloodlines to today's top sires.
            List in under a minute. Free.
          </p>
          <form
            className="searchbar"
            style={{ marginTop: 26 }}
            onSubmit={(e) => { e.preventDefault(); router.push(`/browse?q=${encodeURIComponent(q)}`); }}
          >
            <input
              placeholder="Search Michifuku, Tajima, Itoshigenami…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <button className="btn btn-gold" type="submit">Search</button>
          </form>
          <div className="row wrap" style={{ marginTop: 18, gap: 10 }}>
            <Link href="/sell" className="btn btn-lg btn-gold">List your genetics →</Link>
            <Link href="/history" className="btn btn-lg btn-ghost">Explore the breed history</Link>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="cats">
            <Link href="/browse?product_type=semen" className="cat">
              <div className="glyph">🧬</div>
              <h3>Semen Straws</h3>
              <p className="muted">Conventional & sexed, from proven Wagyu sires worldwide.</p>
            </Link>
            <Link href="/browse?product_type=embryo" className="cat">
              <div className="glyph">🥚</div>
              <h3>Embryos</h3>
              <p className="muted">Full-blood IVF & in-vivo embryos, sire × dam pedigrees.</p>
            </Link>
            <Link href="/browse?product_type=clone_rights" className="cat">
              <div className="glyph">🐂</div>
              <h3>Cloning Rights</h3>
              <p className="muted">License the right to clone a banked cell line. Ours alone.</p>
            </Link>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="section-head">
            <h2>Fresh listings</h2>
            <div className="spacer" />
            <Link href="/browse" className="nav-link">View all →</Link>
          </div>
          {loading ? (
            <div className="grid listings-grid">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="card"><div className="lc-media" /><div className="lc-body"><div className="skeleton" style={{ width: "70%" }} /><div className="skeleton" style={{ width: "40%", marginTop: 10 }} /></div></div>
              ))}
            </div>
          ) : listings.length ? (
            <div className="grid listings-grid">
              {listings.map((l) => <ListingCard key={l.id} l={l} />)}
            </div>
          ) : (
            <div className="adslot">No listings yet — <Link href="/sell" className="gold">be the first to list →</Link></div>
          )}
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="adslot">
            <strong className="gold">WagyuTank</strong> — the effortless way to sell frozen genetics.
            Type a registration number, and we write the ad for you.{" "}
            <Link href="/sell" className="gold">Start selling →</Link>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="section-head">
            <h2>The foundation bulls</h2>
            <div className="spacer" />
            <Link href="/history" className="nav-link">Breed history →</Link>
          </div>
          <p className="muted" style={{ maxWidth: "60ch", marginTop: -10, marginBottom: 20 }}>
            Every full-blood Wagyu in the West descends from a handful of animals that left Japan before the 1997 export ban. They're all here.
          </p>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))" }}>
            {foundation.map((a) => (
              <Link key={a.id} href={`/animal/${encodeURIComponent(a.registration_no || a.name)}`} className="card card-pad">
                <div className="row" style={{ gap: 6, marginBottom: 8 }}>
                  <span className="pill">{a.bloodline}</span>
                </div>
                <div style={{ fontWeight: 700 }}>{a.name}</div>
                <div className="faint" style={{ fontSize: "0.8rem", marginTop: 4 }}>
                  {a.au_progeny ? `${a.au_progeny.toLocaleString()} AU progeny` : a.breed}
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
