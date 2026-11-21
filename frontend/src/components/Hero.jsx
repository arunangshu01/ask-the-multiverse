import { useEffect, useState } from "react";
import { api } from "../api/client";
import { art, medium } from "../lib/media";

// Featured realities: which ones is an editorial choice; every word shown comes from the API.
const FEATURED = ["Earth-616", "Earth-199999", "Earth-92131", "Earth-1048", "Earth-838", "Earth-1610"];
const SLIDE_MS = 7000;

export default function Hero({ onExplore, onAsk }) {
  const [items, setItems] = useState([]);
  const [i, setI] = useState(0);

  useEffect(() => {
    Promise.all(FEATURED.map((id) => api.reality(id).catch(() => null))).then((rs) => setItems(rs.filter((r) => r && !r.redirect)));
  }, []);
  useEffect(() => {
    if (!items.length || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return undefined;
    const t = setTimeout(() => setI((x) => (x + 1) % items.length), SLIDE_MS);
    return () => clearTimeout(t);
  }, [i, items.length]);

  if (!items.length) return <div className="hero" aria-hidden="true" />;
  const r = items[i];
  const m = medium(r.medium);
  const title = r.name || r.id;
  const words = title.split(/\s+/);
  const a = words.length > 3 ? words.slice(0, Math.ceil(words.length / 2)).join(" ") : words[0];
  const rest = words.slice(a.split(" ").length);
  // long names get a smaller headline so the banner never overflows
  const h1 = title.length > 34 ? "clamp(30px, 4.2vw, 64px)" : title.length > 20 ? "clamp(34px, 5.2vw, 80px)" : undefined;
  return (
    <section className="hero" aria-roledescription="carousel" aria-label="Featured realities" >
      {items.map((x, j) => (
        <div key={x.id} className={`slide${j === i ? " on" : ""}`} aria-hidden="true">
          <div className="art" style={{ background: art(x.id) }} /><div className="num">{x.id.replace(/^Earth-/, "")}</div>
        </div>
      ))}
      <div className="hero-copy" key={r.id} aria-live="polite">
        <div className="eyebrow" style={{ "--accent": m.color }}>Featured reality - {m.label}</div>
        <h1 style={h1 ? { "--h1": h1 } : undefined}><span className="line"><span>{a}</span></span>{rest.length > 0 && <span className="line"><span style={{ animationDelay: ".12s" }}>{rest.join(" ")}</span></span>}</h1>
        <div className="meta"><span className="tag">{r.id.toUpperCase()}</span>
          {r.first_appearance && <span>First seen: {r.first_appearance}{r.first_year ? ` (${r.first_year})` : ""}</span>}</div>
        <p>{r.listing_note || r.description}</p>
        <div className="btns">
          <button type="button" className="btn primary" onClick={() => onExplore(r.id)}>&#9654;&nbsp; Explore Reality</button>
          <button type="button" className="btn ghost" onClick={() => onAsk(`Tell me about ${r.id}`)}>Ask About It</button>
        </div>
      </div>
      <div className="dots" role="group" aria-label="Choose a featured reality">
        {items.map((x, j) => <button type="button" key={x.id} className={j === i ? "on" : ""} aria-label={x.id} aria-pressed={j === i} onClick={() => setI(j)} />)}
      </div>
    </section>
  );
}
