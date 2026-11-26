import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { KINDS, MEDIA, STATUSES, TYPES, fmt, medium } from "../lib/media";

const PAGE = 60;

function Tile({ r, onOpen }) {
  const m = medium(r.medium);
  const sub = r.kind === "temporary" ? " - TRN" : r.kind === "dimension" || r.kind === "realm" ? ` - ${KINDS[r.kind]}` : "";
  const first = r.first_appearance ? `First: ${r.first_appearance}${r.first_year ? ` (${r.first_year})` : ""}`
    : r.status === "undocumented" ? "Listed number - no wiki page yet" : "First appearance not recorded";
  return (
    <li>
      <button type="button" className="tile" style={{ "--c": m.color }} onClick={() => onOpen(r.id)}
        aria-label={`${r.name && r.name !== r.id ? `${r.id}, ${r.name}` : r.id}: ${m.label}${sub}`}>
        <div className="id">{r.id}</div>
        <span className="md">{m.label}{sub}</span>
        <div className="nt">{r.name && r.name !== r.id ? <b>{r.name}. </b> : null}
          {r.description || (!r.name && <span className="none">No description on the wiki yet</span>)}</div>
        <div className="fa">{first}</div>
      </button>
    </li>
  );
}

/** "The Complete Multiverse": every reality, dimension and realm, paged from the API. */
export default function IndexGrid({ query, media, onOpen, mediumFilter, setMediumFilter, types }) {
  const [kind, setKind] = useState("all");
  const [type, setType] = useState("all");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("designation");
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(null);
  const [facets, setFacets] = useState({});
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(null); // null | "reset" (filters changed) | "more"
  const reqId = useRef(0);
  const top = useRef(null);

  const effectiveMedium = mediumFilter !== "all" ? mediumFilter : media ? media.join(",") : undefined;
  const params = { q: query.trim() || undefined, medium: effectiveMedium, kind, type, status, sort, limit: PAGE };

  const load = useCallback(async (offset) => {
    const id = ++reqId.current;
    setLoading(offset === 0 ? "reset" : "more");
    try {
      const body = await api.realities({ ...params, offset });
      if (id !== reqId.current) return;
      setTotal(body.total);
      setFacets(body.facets.medium);
      setItems((prev) => (offset === 0 ? body.items : [...prev, ...body.items]));
      setError(null);
    } catch (e) {
      if (id === reqId.current) setError(e.message);
    } finally {
      if (id === reqId.current) setLoading(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(params)]);

  useEffect(() => {
    const t = setTimeout(() => load(0), query ? 200 : 0);
    return () => clearTimeout(t);
  }, [load, query]);

  const visibleMedia = Object.keys(MEDIA).filter((k) => facets[k] && (!media || media.includes(k)));
  const allCount = visibleMedia.reduce((a, k) => a + facets[k], 0);

  return (
    <section id="index" aria-labelledby="index-h" ref={top}>
      <div className="sh">
        <h2 id="index-h">The Complete Multiverse</h2>
        <span className="c" aria-live="polite">
          {total === null ? "Loading..." : `${fmt(total)} ${total === 1 ? "entry" : "entries"} match`}
        </span>
      </div>
      <div className="ixbar">
        <div className="chips" role="group" aria-label="Filter by medium">
          <button type="button" className="chip" aria-pressed={mediumFilter === "all"} onClick={() => setMediumFilter("all")}>
            All<span className="k">{fmt(allCount)}</span>
          </button>
          {visibleMedia.map((k) => (
            <button type="button" key={k} className="chip" aria-pressed={mediumFilter === k} onClick={() => setMediumFilter(k)}>
              {MEDIA[k].label}<span className="k">{fmt(facets[k])}</span>
            </button>
          ))}
        </div>
        <label><span className="sr-only">Kind</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="all">All kinds</option>
            {Object.entries(KINDS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        <label><span className="sr-only">Type</span>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="all">All types</option>
            {(types || Object.keys(TYPES)).map((k) => <option key={k} value={k}>{TYPES[k] || k}</option>)}
          </select>
        </label>
        <label><span className="sr-only">Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="all">Any status</option>
            {Object.entries(STATUSES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        <label><span className="sr-only">Sort</span>
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="designation">Sort: designation</option>
            <option value="year">Sort: debut year</option>
            <option value="described">Sort: best described</option>
          </select>
        </label>
      </div>
      {error && <div className="err" role="alert">Could not load the index: {error}</div>}
      {/* Pages load on request (not on scroll), so the footer below always stays reachable. While filters
          change, the previous cards stay in place (dimmed) and skeleton cards fill in, so the page never jumps. */}
      <ul className={`grid${loading === "reset" && items.length ? " stale" : ""}`} aria-busy={Boolean(loading)}>
        {items.map((r) => <Tile key={r.id} r={r} onOpen={onOpen} />)}
        {(loading === "more" || (loading === "reset" && !items.length)) &&
          Array.from({ length: loading === "more" ? Math.min(10, (total || PAGE) - items.length) : 10 }, (_, i) => (
            <li key={`sk${i}`} aria-hidden="true"><div className="tile skel"><i /><i /><i /></div></li>))}
      </ul>
      <div className="more-bar">
        {total === null ? null : items.length < total ? (
          <>
            <span className="c">Showing {fmt(items.length)} of {fmt(total)}</span>
            <button type="button" className="btn ghost" onClick={() => load(items.length)} disabled={Boolean(loading)}>
              {loading === "more" ? "Loading..." : `Load ${fmt(Math.min(PAGE, total - items.length))} more`}</button>
            {items.length > PAGE && <button type="button" className="chip" onClick={() => top.current?.scrollIntoView({ behavior: "smooth" })}>Back to top</button>}
          </>
        ) : total ? <span className="c">All {fmt(total)} shown</span> : <span className="c">Nothing matches these filters.</span>}
      </div>
    </section>
  );
}
