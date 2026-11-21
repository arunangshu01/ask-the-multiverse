import { useEffect, useState } from "react";
import { api } from "../api/client";
import { MEDIA, art, fmt, medium } from "../lib/media";

function Row({ m, onOpen, onSeeAll }) {
  const [data, setData] = useState(null);
  useEffect(() => { api.realities({ medium: m, sort: "described", limit: 24 }).then(setData).catch(() => setData(null)); }, [m]);
  if (!data || !data.total) return null;
  const meta = MEDIA[m];
  return (
    <section aria-labelledby={`row-${m}`}>
      <div className="sh"><h2 id={`row-${m}`}>{meta.row}</h2><span className="c">{fmt(data.total)} realities</span>
        <button type="button" className="more" onClick={() => onSeeAll(m)}>See all &rsaquo;</button></div>
      <ul className="row">
        {data.items.map((r) => (
          <li key={r.id}>
            <button type="button" className="poster" onClick={() => onOpen(r.id)} aria-label={`${r.id}: ${r.name || ""}`} style={{ "--accent": meta.color }}>
              <div className="art" style={{ background: art(r.id) }} />
              <div className="d"><small>{r.id.includes("TRN") ? "EARTH-TRN" : r.id.split("-")[0].toUpperCase()}</small>{r.id.replace(/^Earth-(TRN)?/, "")}</div>
              <div className="info"><div className="t">{r.name || r.description || r.id}</div>
                <div className="s" style={{ color: medium(r.medium).color }}>{meta.label} - {r.first_appearance || "debut not recorded"}</div></div>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function PosterRows({ media, onOpen, onSeeAll }) {
  const keys = media || ["Film", "Television", "Animation", "Games", "Comics", "Prose"];
  return keys.map((m) => <Row key={m} m={m} onOpen={onOpen} onSeeAll={onSeeAll} />);
}
