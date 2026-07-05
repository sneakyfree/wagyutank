"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import ListingCard from "../../components/ListingCard";

export default function Dashboard() {
  const { user, loading } = useAuth();
  const [listings, setListings] = useState<any[]>([]);

  useEffect(() => { if (user) api.myListings().then(setListings).catch(() => {}); }, [user]);

  if (loading) return <div className="container section">Loading…</div>;
  if (!user) return <div className="container section">Please <Link href="/login" className="gold">sign in</Link>.</div>;

  const views = listings.reduce((s, l) => s + (l.views || 0), 0);

  return (
    <div className="container section">
      <div className="row wrap">
        <div>
          <h1 style={{ fontSize: "1.8rem" }}>{user.display_name}</h1>
          {user.handle && <Link href={`/u/${user.handle}`} className="gold">View my storefront →</Link>}
        </div>
        <div className="spacer" />
        <Link href="/sell" className="btn btn-gold">+ New listing</Link>
      </div>

      <div className="row wrap" style={{ gap: 14, margin: "22px 0" }}>
        <div className="card card-pad" style={{ flex: 1, minWidth: 130 }}><div className="faint">Active listings</div><div className="big-price">{listings.length}</div></div>
        <div className="card card-pad" style={{ flex: 1, minWidth: 130 }}><div className="faint">Total views</div><div className="big-price">{views}</div></div>
        <div className="card card-pad" style={{ flex: 1, minWidth: 130 }}><div className="faint">Seller rating</div><div className="big-price">{user.seller_rating_count ? user.seller_rating.toFixed(1) : "—"}</div></div>
      </div>

      <div className="section-head"><h2>Your listings</h2></div>
      {listings.length ? (
        <div className="grid listings-grid">{listings.map((l) => <ListingCard key={l.id} l={l} />)}</div>
      ) : (
        <div className="adslot">No listings yet. <Link href="/sell" className="gold">Create your first →</Link></div>
      )}
    </div>
  );
}
