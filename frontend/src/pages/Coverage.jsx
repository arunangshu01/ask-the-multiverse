import { useEffect, useState } from "react";
import { api } from "../api/client";
import { KINDS, MEDIA, STATUSES, TYPES, fmt } from "../lib/media";

function Counts({ title, data, labels }) {
  return (
    <div className="panel">
      <h2>{title}</h2>
      <table className="tbl"><tbody>
        {Object.entries(data || {}).map(([k, n]) => (
          <tr key={k}><td>{labels?.[k]?.label || labels?.[k] || k}</td><td className="num">{fmt(n)}</td></tr>
        ))}
      </tbody></table>
    </div>
  );
}

/** Index stats + coverage: real counts, quality checks, every rejected or unclassified page, known gaps. */
export default function Coverage({ stats }) {
  const [cov, setCov] = useState(null);
  const [filter, setFilter] = useState({ stage: "", reason: "", q: "" });
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState(null);

  useEffect(() => {
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      api.coverage({ ...filter, offset, limit: 100 }, { signal: ctrl.signal })
        .then((d) => { setCov(d); setError(null); })
        .catch((e) => e.name !== "AbortError" && setError(e.message));
    }, 150);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [filter, offset]);

  const set = (k) => (e) => { setOffset(0); setFilter((f) => ({ ...f, [k]: e.target.value })); };
  const stages = [...new Set((cov?.summary || []).map((s) => s.stage))];
  const meta = cov?.run?.meta || {};
  return (
    <section aria-labelledby="cov-h">
      <div className="sh"><h1 id="cov-h">Index stats and coverage</h1>
        {stats?.synced_at && <span className="c">Last synced {new Date(stats.synced_at).toUTCString().replace(" GMT", " UTC")}</span>}</div>
      <p className="lede">Every number below is counted from the current snapshot. Pages the ingest rejected or could
        not classify are listed with the reason, so nothing is dropped silently.</p>
      {error && <p className="err" role="alert">{error}</p>}
      {stats && (
        <div className="stats" style={{ marginBottom: 18 }}>
          {[["Entries", stats.total], ["In the official/TRN lists", stats.listed], ["With a wiki page", stats.with_page],
            ["Places inside dimensions", stats.places], ["Wikidata-linked", stats.wikidata_linked],
            ["Ingest issues", stats.issues]].map(([l, n]) => (
            <div className="stat" key={l}><div className="n">{fmt(n)}</div><div className="l">{l}</div></div>
          ))}
        </div>
      )}
      {stats && (
        <div className="cols">
          <Counts title="By medium" data={stats.by_medium} labels={MEDIA} />
          <Counts title="By kind" data={stats.by_kind} labels={KINDS} />
          <Counts title="By status" data={stats.by_status} labels={STATUSES} />
          <Counts title="By type" data={stats.by_type} labels={TYPES} />
        </div>
      )}
      {cov && (
        <>
          <div className="panel">
            <h2>Source measurements (this run)</h2>
            <table className="tbl"><tbody>
              {meta.listing && <>
                <tr><td>Rows in Multiverse/Universe Listing</td><td className="num">{fmt(meta.listing.official_rows)}</td></tr>
                <tr><td>Current entries in List of Temporary Reality Numbers</td><td className="num">{fmt(meta.listing.trn_rows)}</td></tr>
              </>}
              {meta.categories && Object.entries(meta.categories).map(([k, v]) => (
                <tr key={k}><td>{k.replaceAll("_", " ")}</td><td className="num">{fmt(v)}</td></tr>))}
              {meta.works && Object.entries(meta.works).map(([k, v]) => (
                <tr key={k}><td>{k.replaceAll("_", " ")}</td><td className="num">{fmt(v)}</td></tr>))}
              <tr><td>Marvel Database API calls (cache hits)</td><td className="num">{fmt(meta.api_calls)} ({fmt(meta.cache_hits)})</td></tr>
            </tbody></table>
          </div>
          <div className="panel">
            <h2>Quality checks</h2>
            <table className="tbl"><tbody>
              {cov.checks.map((c) => (
                <tr key={c.check}><td className={`st-${c.status}`}>{c.status}</td><td>{c.check}</td><td>{c.detail}</td></tr>
              ))}
            </tbody></table>
          </div>
          <div className="panel">
            <h2>Rejected or unclassified pages ({fmt(cov.total)})</h2>
            <div className="ixbar">
              <label><span className="sr-only">Stage</span>
                <select value={filter.stage} onChange={set("stage")}>
                  <option value="">All stages</option>{stages.map((s) => <option key={s}>{s}</option>)}
                </select></label>
              <label><span className="sr-only">Reason</span>
                <select value={filter.reason} onChange={set("reason")}>
                  <option value="">All reasons</option>
                  {cov.summary.filter((s) => !filter.stage || s.stage === filter.stage).map((s) => (
                    <option key={`${s.stage}${s.reason}`} value={s.reason}>{s.reason} ({fmt(s.n)})</option>))}
                </select></label>
              <label className="search" style={{ width: 240 }}><span className="sr-only">Search pages</span>
                <input type="search" placeholder="Search pages..." value={filter.q} onChange={set("q")} /></label>
            </div>
            <div className="scroll-x">
              <table className="tbl">
                <thead><tr><th>Page</th><th>Stage</th><th>Reason</th><th>Detail</th></tr></thead>
                <tbody>
                  {cov.items.map((i) => (
                    <tr key={`${i.page}|${i.stage}|${i.reason}`}>
                      <td><a href={`https://marvel.fandom.com/wiki/${encodeURIComponent(i.page.replaceAll(" ", "_"))}`}
                        target="_blank" rel="noreferrer">{i.page}</a></td>
                      <td>{i.stage}</td><td>{i.reason}</td><td>{i.detail}</td>
                    </tr>))}
                </tbody>
              </table>
            </div>
            <div className="ixbar" style={{ marginTop: 10 }}>
              <button type="button" className="chip" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}>Previous</button>
              <span className="note">{fmt(cov.total ? offset + 1 : 0)}-{fmt(Math.min(offset + 100, cov.total))} of {fmt(cov.total)}</span>
              <button type="button" className="chip" disabled={offset + 100 >= cov.total} onClick={() => setOffset(offset + 100)}>Next</button>
            </div>
          </div>
          <div className="cols">
            <div className="panel">
              <h2>Reviewed medium overrides ({fmt(cov.overrides.length)})</h2>
              <table className="tbl"><tbody>{cov.overrides.map((o) => (
                <tr key={o.id}><td>{o.id}</td><td>{o.medium}</td><td>{o.medium_source}</td></tr>))}</tbody></table>
              <p className="note">{fmt(cov.keyword_classified)} entries were classified by keywords only (low confidence) and are marked as such.</p>
            </div>
            <div className="panel">
              <h2>Known gaps</h2>
              <ul>{cov.known_gaps.map((g) => <li key={g} className="note" style={{ marginBottom: 6 }}>{g}</li>)}</ul>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
