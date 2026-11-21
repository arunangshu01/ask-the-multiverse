import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { KINDS, STATUSES, TYPES, art, fmt, medium } from "../lib/media";

function RealityLink({ r, onOpen }) {
  if (!r) return null;
  return (
    <button type="button" className="pill" onClick={() => onOpen(r.id)} disabled={r.missing}
      title={r.missing ? "Not in the index" : r.name || r.id}>
      {r.id}{r.name && r.name !== r.id ? ` - ${r.name}` : ""}
    </button>
  );
}

/** Side panel for one reality, dimension or realm. Every fact shown comes from the API row. */
export default function RealityPanel({ id, onClose, onOpen, onEntity, onAsk }) {
  const [data, setData] = useState(null);
  const [chars, setChars] = useState(null);
  const [error, setError] = useState(null);
  const closeRef = useRef(null);

  useEffect(() => {
    setChars(null);
    api.characters({ reality: id, limit: 24 }).then(setChars).catch(() => setChars(null));
  }, [id]);

  useEffect(() => {
    const ctrl = new AbortController();
    setData(null);
    setError(null);
    api.reality(id, { signal: ctrl.signal }).then((d) => {
      if (d.redirect) onOpen(d.redirect, { replace: true });
      else setData(d);
    }).catch((e) => e.name !== "AbortError" && setError(e.message));
    return () => ctrl.abort();
  }, [id, onOpen]);

  useEffect(() => {
    const prev = document.activeElement;
    closeRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); prev?.focus?.(); };
  }, [onClose]);

  const m = medium(data?.medium);
  const isDim = data && (data.kind === "dimension" || data.kind === "realm");
  return (
    <>
      <div className="scrim" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" style={{ "--accent": m.color }}>
        <button type="button" className="x" ref={closeRef} onClick={onClose} aria-label="Close panel">&#10005;</button>
        <div className="ban" style={{ background: art(id) }} role="img" aria-label={`Generated artwork for ${id}`}>
          <div className="n" id="drawer-title">
            <small>{data ? KINDS[data.kind] || data.kind : "Loading"}</small>{id}
          </div>
        </div>
        <div className="bd">
          {error && <p className="err" role="alert">{error}</p>}
          {!data && !error && <p className="note">Loading...</p>}
          {data && (
            <>
              <div className="tags">
                <span className="tag" style={{ borderColor: m.color, color: m.color }}>{m.label}</span>
                {data.status && data.status !== "bucket" && <span className="tag">{STATUSES[data.status] || data.status}</span>}
                {data.types.map((t) => <span className="tag" key={t}>{TYPES[t] || t}</span>)}
              </div>
              {data.name && data.name !== id && <h3 style={{ marginTop: 14 }}>{data.name}</h3>}
              <p className="desc">{data.description || "The wiki has no description for this entry yet."}</p>
              {data.description_shortened && <p className="note">Shortened from the wiki's text - see the source for the full history.</p>}
              {data.listing_note && data.description_source === "page" && (
                <p className="note">Listing note: {data.listing_note}</p>
              )}
              <dl>
                <dt>First appearance</dt>
                <dd>{data.first_appearance || "Not recorded"}{data.first_year ? ` (${data.first_year})` : ""}
                  {data.year_source && <div className="note">Year from {data.year_source}</div>}</dd>
                <dt>Medium</dt>
                <dd>{m.label}{data.medium_format ? ` - ${data.medium_format}` : ""}
                  {data.medium_source && <div className="note">Based on {data.medium_source}</div>}</dd>
                {data.designation && data.designation !== id && <><dt>Designation</dt><dd>{data.designation}</dd></>}
                {data.listing_kind && <><dt>Listed in</dt><dd>{data.listing_kind === "temporary"
                  ? "List of Temporary Reality Numbers (wiki-assigned)" : "Multiverse/Universe Listing (official numbers)"}</dd></>}
                {data.parents.length > 0 && <><dt>{isDim ? "Part of" : "Branched from"}</dt>
                  <dd>{data.parents.map((p) => <RealityLink key={p.id} r={p} onOpen={onOpen} />)}</dd></>}
                {data.home_reality && <><dt>Reality</dt><dd>{data.home_reality}</dd></>}
                {data.destroyed_by.length > 0 && <><dt>Destroyed by</dt><dd>{data.destroyed_by.join(", ")}</dd></>}
                {data.creators.length > 0 && <><dt>Creators</dt><dd>{data.creators.join(", ")}</dd></>}
                {data.aliases.length > 0 && <><dt>Also called</dt><dd>{data.aliases.join(", ")}</dd></>}
                {data.bucket_size ? <><dt>Characters</dt><dd>{fmt(data.bucket_size)} character pages with an unknown home reality</dd></> : null}
                {data.qid && <><dt>Wikidata</dt><dd>{data.qid}</dd></>}
              </dl>
              {data.children.length > 0 && <>
                <h3>{isDim ? "Contains" : "Realities branched from it"} ({fmt(data.children.length)})</h3>
                <div>{data.children.map((c) => <RealityLink key={c.id} r={c} onOpen={onOpen} />)}</div>
              </>}
              {data.related.length > 0 && <>
                <h3>Related realities</h3>
                <p className="note">Mentioned together on the wiki.</p>
                <div>{data.related.map((c) => <RealityLink key={c.id} r={c} onOpen={onOpen} />)}</div>
              </>}
              {data.places_total > 0 && <>
                <h3>Places in it ({fmt(data.places_total)})</h3>
                <div>{data.places.map((p) => (
                  <a className="pill" key={p.id} href={p.url} target="_blank" rel="noreferrer">{p.name}</a>
                ))}{data.places_total > data.places.length && <span className="note">and {fmt(data.places_total - data.places.length)} more</span>}</div>
              </>}
              <h3>Sources</h3>
              <ul className="sources">
                {data.sources.map((s) => (
                  <li key={s.url}>
                    <a href={s.url} target="_blank" rel="noreferrer">{s.label} &#8599;</a>
                    {s.permalink && <> - <a href={s.permalink} target="_blank" rel="noreferrer">revision used</a></>}
                  </li>
                ))}
              </ul>
              {chars && chars.total > 0 && <>
                <h3>Characters from it ({fmt(chars.total)})</h3>
                <div>{chars.items.map((c) => (
                  <button type="button" className="pill" key={c.id} onClick={() => onEntity?.(c.id)} title={c.id}>{c.label}</button>
                ))}</div>
                {chars.total > chars.items.length && <p className="note">Showing the {chars.items.length} with the most story appearances.</p>}
              </>}
              <div className="btns" style={{ marginTop: 18 }}>
                <button type="button" className="btn primary" onClick={() => { onClose(); onAsk?.(`Tell me about ${id}`); }}>Ask About It</button>
              </div>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
