"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "../../../lib/api";
import ListingCard from "../../../components/ListingCard";

export default function Storefront() {
  const { handle } = useParams<{ handle: string }>();
  const [data, setData] = useState<any>(null);

  useEffect(() => { api.storefront(handle).then(setData).catch(() => setData(false)); }, [handle]);

  if (data === false) return <div className="container section">Storefront not found.</div>;
  if (!data) return <div className="container section">Loading…</div>;
  const s = data.seller;
  const stars = Math.round(s.seller_rating || 0);

  return (
    <div className="container section">
      <div className="row" style={{ gap: 16 }}>
        <div className="avatar">{(s.display_name || "?")[0].toUpperCase()}</div>
        <div>
          <h1 style={{ fontSize: "1.8rem", marginBottom: 2 }}>{s.display_name}</h1>
          <div className="muted">
            {s.handle && <span>@{s.handle} · </span>}{s.location || "Wagyu genetics"}
            {s.seller_rating_count > 0 && <span> · <span className="stars">{"★".repeat(stars)}{"☆".repeat(5 - stars)}</span> ({s.seller_rating_count})</span>}
          </div>
        </div>
        <div className="spacer" />
        <button className="btn">+ Follow</button>
      </div>
      {s.bio && <p className="muted" style={{ marginTop: 14, maxWidth: "70ch" }}>{s.bio}</p>}

      <div className="section-head" style={{ marginTop: 30 }}>
        <h2>{data.listing_count} listing{data.listing_count === 1 ? "" : "s"}</h2>
      </div>
      {data.listings.length ? (
        <div className="grid listings-grid">{data.listings.map((l: any) => <ListingCard key={l.id} l={l} />)}</div>
      ) : (
        <div className="adslot">No active listings.</div>
      )}
    </div>
  );
}
