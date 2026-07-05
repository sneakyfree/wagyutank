# WagyuTank.com

The world's marketplace for frozen Wagyu genetics — **semen straws, embryos, and cloning/cell-line rights.**

Free to list. One account buys and sells. Type a registration number, drag a screenshot, and an AI writes your ad — a professional, shareable, registry-linked listing in under a minute.

See [`MASTER_PLAN.md`](./MASTER_PLAN.md) for the full product genome and [`SPEC.md`](./SPEC.md) for detailed research.

## Repo layout (this is the **backend** repo — private)

```
wagyutank/                (private) — this repo: the API + planning docs
├── backend/              FastAPI + SQLAlchemy — canonical Animal spine, listings, auctions, accounts, payments, AI
├── MASTER_PLAN.md        product genome
├── SPEC.md               research
└── outreach-emails.md    Helical / AWA outreach drafts (keep private)
```

The **frontend** lives in a separate public repo: [`sneakyfree/wagyutank-site`](https://github.com/sneakyfree/wagyutank-site) → deploys to Cloudflare Pages at `www.wagyutank.com`.

**Deploy topology:** GitHub `main` is canonical. The VPS clones this repo and runs `backend/` as a systemd service on port 8120, reverse-proxied by nginx at `https://api.wagyutank.com` (Cloudflare-fronted). The site repo deploys to Cloudflare Pages.

## Backend — quick start

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.seed.seed      # loads foundation animals + facility directory
uvicorn app.main:app --reload --port 8100
# API docs at http://localhost:8100/docs
```

Dev uses SQLite by default (`DATABASE_URL` in `.env`). Point `DATABASE_URL` at Postgres for production.

## Frontend — quick start

```bash
cd frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_BASE -> backend URL
npm run dev                         # http://localhost:3000
```

Next.js (App Router, React 19), mobile-first, client-rendered against the API. Pages:
`/` home · `/browse` faceted search · `/sell` the 60-second listing flow ·
`/listing/[id]` · `/animal/[reg]` (canonical page + multi-seller offers) ·
`/u/[handle]` storefront · `/history` breed history · `/login` · `/register` · `/dashboard`.

## Architecture principle: the Animal is the atom

Every registration number is **one canonical `Animal` record** (pedigree, photos, history). Listings, offers, the pedigree cache, the pre-loaded foundation registry, and the public SEO/animal pages are all *views* of that one table. Build the spine once; the features fall out of it.

## Status

Early build — MVP scaffold. See `MASTER_PLAN.md` §20 for phasing.
