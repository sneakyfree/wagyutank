"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "../../../lib/api";
import ListingCard from "../../../components/ListingCard";

export default function AnimalPage() {
  const { reg } = useParams<{ reg: string }>();
  const [a, setA] = useState<any>(null);
  const [offers, setOffers] = useState<any[]>([]);

  useEffect(() => {
    api.animal(reg).then(setA).catch(() => setA(false as any));
    api.animalOffers(reg).then(setOffers).catch(() => {});
  }, [reg]);

  if (a === false) return <div className="container section">Animal not found.</div>;
  if (!a) return <div className="container section">Loading…</div>;

  return (
    <div className="container section">
      <div className="row wrap" style={{ gap: 8, marginBottom: 8 }}>
        {a.is_foundation && <span className="pill">Foundation animal</span>}
        {a.bloodline && <span className="pill pill-dim">{a.bloodline}</span>}
        <span className="pill pill-dim">{a.breed}</span>
      </div>
      <h1 style={{ fontSize: "2.2rem" }}>{a.name}</h1>
      <div className="muted" style={{ fontSize: "1rem" }}>
        {a.registration_no && <span>Reg. {a.registration_no} · </span>}
        {a.animal_type}{a.birth_year ? ` · b. ${a.birth_year}` : ""}
      </div>

      {a.notable && <p className="muted" style={{ maxWidth: "70ch", marginTop: 14, fontSize: "1.08rem" }}>{a.notable}</p>}

      <div className="row wrap" style={{ gap: 30, marginTop: 24, alignItems: "flex-start" }}>
        <div style={{ flex: "1 1 300px" }}>
          <h2 style={{ fontSize: "1.2rem" }}>Registry record</h2>
          <div className="kv"><span className="k">Bloodline</span><span>{a.bloodline_detail || a.bloodline || "—"}</span></div>
          <div className="kv"><span className="k">Breed</span><span>{a.breed || "—"}</span></div>
          {a.importer && <div className="kv"><span className="k">Importer</span><span>{a.importer}</span></div>}
          {a.import_year && <div className="kv"><span className="k">Imported</span><span>{a.import_year}</span></div>}
          {a.au_progeny != null && <div className="kv"><span className="k">AU progeny</span><span>{a.au_progeny.toLocaleString()}</span></div>}
          {(a.sire_name || a.dam_name) && (
            <>
              <div className="kv"><span className="k">Sire</span><span>{a.sire_name || a.sire_reg || "—"}</span></div>
              <div className="kv"><span className="k">Dam</span><span>{a.dam_name || a.dam_reg || "—"}</span></div>
            </>
          )}
        </div>
        <div style={{ flex: "1 1 300px" }}>
          <div className="adslot" style={{ textAlign: "left" }}>
            <strong className="gold">Own genetics from {a.name}?</strong>
            <p className="muted" style={{ marginTop: 6 }}>List your straws, embryos, or cloning rights in under a minute.</p>
            <Link href="/sell" className="btn btn-gold" style={{ marginTop: 8 }}>List {a.name} genetics →</Link>
          </div>
        </div>
      </div>

      <div className="section" style={{ paddingBottom: 0 }}>
        <div className="section-head">
          <h2>{offers.length} {offers.length === 1 ? "offer" : "offers"} for {a.name}</h2>
        </div>
        {offers.length ? (
          <div className="grid listings-grid">{offers.map((l) => <ListingCard key={l.id} l={l} />)}</div>
        ) : (
          <div className="adslot">No live offers for {a.name} right now. <Link href="/sell" className="gold">Be the first to list →</Link></div>
        )}
      </div>
    </div>
  );
}
