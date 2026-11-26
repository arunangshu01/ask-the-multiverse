import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";

export const EDGE_COLORS = { enemy: "#e62429", team: "#a78bfa", variant: "#38bdf8", ally: "#fbbf24", family: "#34d399" };
const KIND_COLORS = { character: "#f2f2f4", team: "#a78bfa", organization: "#a78bfa", event: "#fbbf24" };
const MAX_NODES = 70;
const PAGE = 40;
const SEARCH_KINDS = "character,team,organization,event";
const shortLabel = (n) => (n.label || n.id).replace(/ \((Earth|Moira)-[^)]*\)$/, "");
const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Star-map of real relationships: nearest neighbours of one node, expanded on click (never the whole graph). */
export default function Graph({ center, highlight, onOpen }) {
  const sky = useRef(null);
  const sim = useRef({ nodes: new Map(), edges: [], alpha: 1, drag: null });
  const [, setTick] = useState(0);
  const [focus, setFocus] = useState(center);
  const [hl, setHl] = useState(null);
  const [query, setQuery] = useState("");
  const [sug, setSug] = useState([]);
  const [sugTotal, setSugTotal] = useState(0);
  const loadingMore = useRef(false);
  const [error, setError] = useState(null);
  const [reality, setReality] = useState("all");

  const size = () => ({ w: sky.current?.clientWidth || 700, h: sky.current?.clientHeight || 480 });

  const addNodes = useCallback((nodes, edges, around) => {
    const s = sim.current;
    const { w, h } = size();
    const origin = (around && s.nodes.get(around)) || { x: w / 2, y: h / 2 };
    nodes.forEach((n, i) => {
      if (s.nodes.has(n.id) || s.nodes.size >= MAX_NODES) return;
      const a = (i / Math.max(1, nodes.length)) * Math.PI * 2;
      s.nodes.set(n.id, { ...n, x: origin.x + Math.cos(a) * (80 + (i % 3) * 60), y: origin.y + Math.sin(a) * (80 + (i % 3) * 60), vx: 0, vy: 0 });
    });
    edges.forEach((e) => {
      if (s.nodes.has(e.a) && s.nodes.has(e.b) && !s.edges.some((x) => (x.a === e.a && x.b === e.b) || (x.a === e.b && x.b === e.a))) s.edges.push(e);
    });
    s.alpha = 1;
  }, []);

  const load = useCallback(async (id, { reset = false } = {}) => {
    try {
      const g = await api.neighbourhood(id);
      if (reset) { sim.current.nodes = new Map(); sim.current.edges = []; }
      addNodes(g.nodes, g.edges, id);
      setFocus(id);
      setError(null);
    } catch (e) {
      setError(e.status === 404 ? `${id} is not in the graph.` : e.message);
    }
  }, [addNodes]);

  useEffect(() => { if (center) load(center, { reset: true }); }, [center, load]);

  // highlight nodes/edges from a console answer
  useEffect(() => {
    if (!highlight?.nodes?.length) return;
    api.nodes(highlight.nodes).then(({ nodes }) => {
      sim.current.nodes = new Map(); sim.current.edges = [];
      addNodes(nodes, (highlight.edges || []).map(([a, b]) => ({ a, b, kind: highlight.kind || "team" })));
      setFocus(highlight.nodes[0]);
      setHl(new Set(highlight.nodes));
    }).catch(() => {});
  }, [highlight, addNodes]);

  // physics loop
  useEffect(() => {
    let raf;
    const step = () => {
      const s = sim.current;
      const { w, h } = size();
      const ns = [...s.nodes.values()];
      if (s.alpha > 0.02 || s.drag) {
        for (const a of ns) for (const b of ns) {
          if (a === b) continue;
          const dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy + 0.01, d = Math.sqrt(d2), f = (9000 / d2) * s.alpha;
          a.vx += (dx / d) * f; a.vy += (dy / d) * f;
        }
        for (const e of s.edges) {
          const a = s.nodes.get(e.a), b = s.nodes.get(e.b);
          if (!a || !b) continue;
          const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1, k = (d - 140) * 0.02 * s.alpha;
          a.vx += (dx / d) * k; a.vy += (dy / d) * k; b.vx -= (dx / d) * k; b.vy -= (dy / d) * k;
        }
        for (const n of ns) {
          n.vx += (w / 2 - n.x) * 0.003; n.vy += (h / 2 - n.y) * 0.004;
          if (n === s.drag) { n.vx = n.vy = 0; continue; }
          n.vx *= 0.8; n.vy *= 0.8; n.x += n.vx; n.y += n.vy;
          // keep labels clear of the edges and of the legend (wider margins on narrow screens)
          const mx = w < 520 ? 64 : 40, mb = w < 520 ? 64 : 40;
          n.x = Math.max(mx, Math.min(w - mx, n.x)); n.y = Math.max(w < 520 ? 104 : 56, Math.min(h - mb, n.y));
        }
        s.alpha = Math.max(0, s.alpha * (reduced() ? 0.9 : 0.985));
        setTick((t) => t + 1);
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, []);

  // every match across all realities, fetched a page at a time as the list scrolls
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) { setSug([]); setSugTotal(0); return undefined; }
    const ctrl = new AbortController();
    const t = setTimeout(() => api.search(q, { signal: ctrl.signal }, { kinds: SEARCH_KINDS, limit: PAGE })
      .then((r) => { setSug(r.items); setSugTotal(r.total); }).catch(() => {}), 200);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [query]);

  const moreSug = useCallback(() => {
    const q = query.trim();
    if (loadingMore.current || sug.length >= sugTotal || q.length < 2) return;
    loadingMore.current = true;
    api.search(q, {}, { kinds: SEARCH_KINDS, limit: PAGE, offset: sug.length })
      .then((r) => { if (r.offset === sug.length) setSug((prev) => [...prev, ...r.items]); })
      .catch(() => {}).finally(() => { loadingMore.current = false; });
  }, [query, sug.length, sugTotal]);

  const pick = (id) => { setQuery(""); setSug([]); setSugTotal(0); setHl(null); load(id, { reset: true }); };

  const startDrag = (e, n) => {
    const s = sim.current;
    const rect = sky.current.getBoundingClientRect();
    s.drag = n; s.alpha = Math.max(s.alpha, 0.4);
    const move = (ev) => { const p = ev.touches ? ev.touches[0] : ev; n.x = p.clientX - rect.left; n.y = p.clientY - rect.top; };
    const up = () => { s.drag = null; window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };

  const s = sim.current;
  const nodes = [...s.nodes.values()].filter((n) => reality === "all" || n.reality === reality || n.id === focus);
  const visible = new Set(nodes.map((n) => n.id));
  const realities = [...new Set([...s.nodes.values()].map((n) => n.reality).filter(Boolean))].sort();
  const isHl = (id) => !hl || hl.has(id);

  return (
    <div className="glass graph-panel" aria-labelledby="graph-h">
      <div className="hd"><span className="live" aria-hidden="true" /><h2 id="graph-h" style={{ font: "inherit", margin: 0 }}>Connections</h2>
        <span className="r">{s.nodes.size} nodes - real relationships</span></div>
      <div className="sky" ref={sky}>
        <div className="stars" aria-hidden="true" /><div className="stars2" aria-hidden="true" /><div className="rings" aria-hidden="true" />
        <div className="ucap">
          <span>FOCUS <b>{focus ? shortLabel(s.nodes.get(focus) || { id: focus }) : "-"}</b></span>
          <label><span className="sr-only">Find a character or team</span>
            <input type="search" placeholder="Find a character..." value={query} onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Escape") setQuery(""); if (e.key === "Enter" && sug[0]) pick(sug[0].id); }} /></label>
          <label><span className="sr-only">Filter by reality</span>
            <select value={reality} onChange={(e) => setReality(e.target.value)} style={{ background: "rgba(0,0,0,.5)", color: "#ddd", border: "1px solid var(--line)", borderRadius: 5, padding: "4px 6px", fontSize: 12 }}>
              <option value="all">All realities</option>
              {realities.map((r) => <option key={r}>{r}</option>)}
            </select></label>
          {hl && <button type="button" className="ghostbtn" onClick={() => setHl(null)}>CLEAR HIGHLIGHT</button>}
        </div>
        {query.trim().length >= 2 && (
          <div className="gsug" role="group" aria-label="Matches across all realities"
            onScroll={(e) => { const el = e.currentTarget; if (el.scrollTop + el.clientHeight > el.scrollHeight - 80) moreSug(); }}>
            <div className="gsug-hd">{sugTotal ? `${sugTotal.toLocaleString()} match${sugTotal === 1 ? "" : "es"} across all realities` : "No matches"}</div>
            <ul>{sug.map((x) => (
              <li key={x.id}><button type="button" onClick={() => pick(x.id)}>
                <span className="gl">{x.label}{x.label !== x.id ? <small> - {x.id}</small> : null}</span>
                <span className="gm">{x.kind !== "character" ? `${x.kind} - ` : ""}{x.reality || ""}{x.appearances ? ` - ${x.appearances.toLocaleString()} apps` : ""}{x.via_alias ? " - alias match" : ""}</span>
              </button></li>))}</ul>
            {sug.length < sugTotal && <button type="button" className="gsug-more" onClick={moreSug}>Show more ({(sugTotal - sug.length).toLocaleString()} left)</button>}
          </div>
        )}
        <svg role="img" aria-label={`Relationship graph centred on ${focus || "nothing"}`}>
          <defs><filter id="glowf" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="4" /></filter></defs>
          <g>
            {s.edges.filter((e) => visible.has(e.a) && visible.has(e.b)).map((e) => {
              const a = s.nodes.get(e.a), b = s.nodes.get(e.b);
              const on = hl && hl.has(e.a) && hl.has(e.b);
              return <line key={`${e.a}|${e.b}|${e.kind}`} className={`edge${on ? " hl" : ""}${hl && !on ? " dim" : ""}`}
                x1={a.x} y1={a.y} x2={b.x} y2={b.y} style={{ stroke: EDGE_COLORS[e.kind], strokeOpacity: on ? 1 : 0.45 }} />;
            })}
          </g>
          <g>
            {nodes.map((n) => {
              const r = Math.min(12, 4 + Math.log10(1 + (n.appearances || 0)) * 2.4);
              const c = KIND_COLORS[n.kind] || "#ddd";
              return (
                <g key={n.id} className={`node${n.id === focus ? " center" : ""}${hl && hl.has(n.id) ? " hl" : ""}${!isHl(n.id) ? " dim" : ""}`}
                  transform={`translate(${n.x},${n.y})`} tabIndex={0} role="button"
                  aria-label={`${n.label || n.id}, ${n.kind}${n.reality ? `, ${n.reality}` : ""}. Enter to open, space to expand.`}
                  onPointerDown={(e) => startDrag(e, n)}
                  onClick={() => { onOpen?.(n.id); load(n.id); }}
                  onKeyDown={(e) => { if (e.key === "Enter") onOpen?.(n.id); if (e.key === " ") { e.preventDefault(); load(n.id); } }}>
                  <circle className="glow" r={r * 2.2} fill={c} filter="url(#glowf)" />
                  <circle className="core" r={r} fill={c} />
                  <circle r={r * 0.45} fill="#fff" fillOpacity=".85" />
                  <text y={r + 14}>{shortLabel(n).slice(0, size().w < 520 ? 14 : 22)}{n.reality && n.reality !== "Earth-616" ? ` - ${n.reality.replace("Earth-", "")}` : ""}</text>
                </g>
              );
            })}
          </g>
        </svg>
        {error && <div className="gempty">{error}</div>}
        {!error && s.nodes.size === 0 && <div className="gempty">Loading connections...</div>}
        <div className="legend" aria-hidden="true">
          {Object.entries(EDGE_COLORS).map(([k, c]) => <span key={k} style={{ "--c": c }}>{k[0].toUpperCase() + k.slice(1)}</span>)}
        </div>
      </div>
    </div>
  );
}
