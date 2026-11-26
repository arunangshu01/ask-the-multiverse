import { useEffect, useState } from "react";
import { api } from "../api/client";
import { art } from "../lib/media";

const KIND = { film: "Film", series: "Series", special: "Special", "one-shot": "One-Shot", short: "Short", "digital series": "Digital series" };

/** MCU (Earth-199999) phases from the MCU Wiki, each title linked to its Marvel Database page when it matched exactly. */
export default function Timeline({ onAsk, onReality }) {
  const [data, setData] = useState(null);
  const [phase, setPhase] = useState(0);
  useEffect(() => { api.timeline().then(setData).catch(() => setData(null)); }, []);
  if (!data?.phases?.length) return null;
  const p = data.phases[Math.min(phase, data.phases.length - 1)];
  return (
    <section aria-labelledby="tl-h" className="timeline">
      <div className="sh"><h2 id="tl-h">MCU Timeline</h2>
        <span className="c">Earth-199999 phases from the MCU Wiki - {data.linked} of {data.total} titles linked to Marvel Database pages</span>
        <button type="button" className="more" onClick={() => onReality?.("Earth-199999")}>Earth-199999 &rsaquo;</button></div>
      <div className="tl-phases" role="tablist" aria-label="MCU phases">
        {data.phases.map((x, i) => (
          <button type="button" role="tab" key={x.phase} aria-selected={i === phase} className={`tl-tab${i === phase ? " on" : ""}`} onClick={() => setPhase(i)}>
            <b>{x.phase.replace("Phase ", "")}</b><span>{x.start_year}{x.end_year && x.end_year !== x.start_year ? `-${x.end_year}` : ""}</span>
          </button>
        ))}
      </div>
      <div role="tabpanel" aria-label={p.phase}>
        <p className="tl-meta">{p.phase}{p.saga ? ` - ${p.saga}` : ""} - <a href={p.permalink || p.url} target="_blank" rel="noreferrer">MCU Wiki phase page &#8599;</a></p>
        <ol className="tl-list">
          {p.entries.map((e) => (
            <li key={`${e.position}-${e.title}`} className="tl-item">
              <div className="tl-art" style={{ background: art(e.work || e.title) }} aria-hidden="true" />
              <div className="tl-body">
                <div className="tl-k">{KIND[e.kind] || e.kind}{e.season ? ` - Season ${e.season}` : ""}{e.year ? ` - ${e.year}` : ""}</div>
                <div className="tl-t">{e.title}</div>
                <div className="tl-l">
                  <a href={e.mcu_url} target="_blank" rel="noreferrer">MCU Wiki</a>
                  {e.work_url ? <> - <a href={e.work_url} target="_blank" rel="noreferrer">Marvel Database</a></>
                    : <> - <span className="tl-un" title="No Marvel Database page with this exact title; listed on the Coverage page">not linked</span></>}
                  {e.work && e.kind !== "series" && onAsk && <> - <button type="button" className="tl-ask" onClick={() => onAsk(`Who appears in ${e.work}?`)}>Ask</button></>}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
