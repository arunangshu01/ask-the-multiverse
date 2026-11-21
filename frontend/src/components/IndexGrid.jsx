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
  const [loading, setLoading] = useState(false);
  const sentinel = useRef(null);
  const reqId = useRef(0);

  const effectiveMedium = mediumFilter !== "all" ? mediumFilter : media ? media.join(",") : undefined;
  const params = { q: query.trim() || undefined, medium: effectiveMedium, kind, type, status, sort, limit: PAGE };

  const load = useCallback(async (offset) => {
    const id = ++reqId.current;
    setLoading(true);
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
      if (id === reqId.current) setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(params)]);

  useEffect(() => {
    const t = setTimeout(() => load(0), query ? 200 : 0);
    return () => clearTimeout(t);
  }, [load, query]);

  useEffect(() => {
    const el = sentinel.current;
    if (!el || typeof IntersectionObserver === "undefined") return undefined;
    const io = new IntersectionObserver((es) => {
      if (es[0].isIntersecting && !loading && total !== null && items.length < total) load(items.length);
    }, { rootMargin: "600px" });
    io.observe(el);
    return () => io.disconnect();
  }, [items.length, total, loading, load]);

  const visibleMedia = Object.keys(MEDIA).filter((k) => facets[k] && (!media || media.includes(k)));
  const allCount = visibleMedia.reduce((a, k) => a + facets[k], 0);

  return (
    <section id="index" aria-labelledby="index-h">
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
      <ul className="grid">
        {items.map((r) => <Tile key={r.id} r={r} onOpen={onOpen} />)}
      </ul>
      <div className="sentinel" ref={sentinel}>
        {total === null ? "" : items.length < total
          ? <button type="button" className="chip" onClick={() => load(items.length)} disabled={loading}>
            {loading ? "Loading..." : `Load more (${fmt(items.length)} of ${fmt(total)})`}</button>
          : total ? `All ${fmt(total)} shown` : "Nothing matches these filters."}
      </div>
    </section>
  );
}
