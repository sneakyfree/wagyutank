# One-shot data migrations — spent, kept for provenance

These scripts have already been run. Their output is committed in
`backend/app/seed/data/`. **Do not re-run them** — they are one-shot transforms
against a specific state of the seed files, not idempotent jobs.

They are kept because they are the *audit trail* for the foundation roster: they
record where each figure came from. WagyuTank's credibility rests on that data
being sourced rather than guessed, and if a breeder disputes an import year or a
bloodline percentage two years from now, the answer is in here.

Both lived untracked on Veron until 2026-07-28, i.e. one disk failure from gone.

| script | ran | what it did |
|---|---|---|
| `vbarv_merge.py` | 2026-07-20 | Merged the V-Bar-V *Semen Services Fall 2009 Sire Directory* into the foundation bull records and photo map. Every field it wrote carries a `(V-Bar-V Semen Services Fall 2009 Sire Directory)` source note. |
| `origins_merge.py` | 2026-07-21 | Grant's corrections to the roster: reclassified bulls **not** born in Japan so they drop out of "Original import foundation sires"; stamped `birth_country` / `importer` / `import_year` from Grant's two Wagyu International export charts; attached the official 16/16 bloodline analysis where a sourced figure existed — Grant's 16/16 chart first, the V-Bar-V catalog as fallback. Its own docstring: **"Never invented."** |

Resulting commits (`foundation_bulls_enriched.json`, `animal_photos.json`):

- `b3e7d24` 2026-07-21 — bloodline schema, ranch marks, Roundup photos
- `4161efa` 2026-07-22 — reference-price regs; **V-Bar-V attribution scrubbed from
  public display** (the directory informed our data; we do not credit it on the
  site — see the project notes)
- `cce9bfa` 2026-07-22 — merged duplicate Big Al, foundation entry gets reg AF11
- `54b550c` 2026-07-23 — Big Al photo mapping
- `a46a235` 2026-07-23 — `semen_only` for 4 sires; Westholme semen year → 1998
- `3baec85` 2026-07-23 — merged duplicate Shigefuku (canonical reg FB6538)

Note the paths inside `vbarv_merge.py` are absolute to Veron
(`/home/user1-gpu/wagyutank/...`). Left exactly as run — this is a record of what
happened, not a script to maintain.
