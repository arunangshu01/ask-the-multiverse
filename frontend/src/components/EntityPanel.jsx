import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { art, fmt } from "../lib/media";

const ROLE = { member: "member", former_member: "former member", leader: "leader", former_leader: "former leader" };
const SIDE = { event_protagonist: "Protagonists", event_antagonist: "Antagonists", event_other: "Others" };
const PROFILE = [["origin", "Origin"], ["place_of_birth", "Born"], ["citizenship", "Citizenship"], ["occupation", "Occupation"],
  ["base", "Base of operations"], ["marital_status", "Marital status"], ["powers", "Powers"], ["abilities", "Abilities"],
  ["death", "Died in"], ["cause_of_death", "Cause of death"]];
const has = (v) => (Array.isArray(v) ? v.length > 0 : Boolean(v));

function Pills({ items, onOpen, label = (x) => x.label || x.id, title }) {
  return <div>{items.map((x) => (
    <button type="button" className="pill" key={`${x.id}${x.type || ""}`} onClick={() => onOpen(x.id)} title={title?.(x) || x.id}>{label(x)}</button>
  ))}</div>;
}

/** Character, team or event panel: names, home reality, first appearance, creators, teams, family, variants, sources. */
export default function EntityPanel({ id, onClose, onOpen, onReality, onAsk }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  const closeRef = useRef(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setD(null); setError(null);
    api.entity(id, { signal: ctrl.signal }).then(setD).catch((e) => e.name !== "AbortError" && setError(e.message));
    return () => ctrl.abort();
  }, [id]);

  useEffect(() => {
    const prev = document.activeElement;
    closeRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); prev?.focus?.(); };
  }, [onClose]);

  const title = d ? (d.current_alias || d.name || id) : id;
  const ask = (q) => { onClose(); onAsk?.(q); };
  return (
    <>
      <div className="scrim" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="entity-title">
        <button type="button" className="x" ref={closeRef} onClick={onClose} aria-label="Close panel">&#10005;</button>
        <div className="ban" style={{ background: art(id) }} role="img" aria-label={`Generated artwork for ${id}`}>
          <div className="n" id="entity-title"><small>{d ? d.kind : "Loading"}</small>{title}</div>
        </div>
        <div className="bd">
          {error && <p className="err" role="alert">{error}</p>}
          {!d && !error && <p className="note">Loading...</p>}
          {d && (
            <>
              <div className="tags">
                <span className="tag">{d.kind}</span>
                {d.reality && <button type="button" className="tag" style={{ background: "none", cursor: "pointer" }} onClick={() => onReality(d.reality)}>{d.reality}</button>}
                {d.appearances > 0 && <span className="tag">{fmt(d.appearances)} story appearances</span>}
              </div>
              <h3 style={{ marginTop: 14 }}>{id}</h3>
              <p className="desc">{d.description || "The wiki page has no overview for this entry."}</p>
              {d.description_shortened && <p className="note">Shortened from the wiki's text - see the source for more.</p>}
              {d.kind === "character" && PROFILE.some(([k]) => has(d[k])) && <><h3>Who they are</h3>
                <dl className="profile">{PROFILE.filter(([k]) => has(d[k])).map(([k, label]) => (
                  <div key={k}><dt>{label}</dt><dd>{Array.isArray(d[k]) ? d[k].join(", ") : d[k]}</dd></div>))}</dl></>}
              {d.origin_story && <><h3>Origin story</h3><p className="desc">{d.origin_story}</p>
                <p className="note">The opening of the History section on the wiki, shortened.</p></>}
              <dl>
                {d.name && d.name !== title && <><dt>Name</dt><dd>{d.name}</dd></>}
                {d.aliases?.length > 0 && <><dt>Also known as</dt><dd>{d.aliases.slice(0, 14).join(", ")}{d.aliases.length > 14 ? ` and ${d.aliases.length - 14} more` : ""}</dd></>}
                <dt>Home reality</dt><dd>{d.reality ? <button type="button" className="pill" onClick={() => onReality(d.reality)}>{d.reality}</button> : "Unknown"}</dd>
                <dt>First appearance</dt><dd>{d.first_appearance || "Not recorded"}{d.first_work_year ? ` (${d.first_work_year})` : ""}</dd>
                {d.creators?.length > 0 && <><dt>Creators</dt><dd>{d.creators.join(", ")}</dd></>}
                {d.gender && <><dt>Gender</dt><dd>{d.gender}</dd></>}
                {d.last_appearance && <><dt>Last appearance</dt><dd>{d.last_appearance}</dd></>}
              </dl>
              {d.teams?.length > 0 && <><h3>Teams ({fmt(d.teams.length)})</h3>
                <Pills items={d.teams} onOpen={onOpen} label={(t) => `${t.label}${t.roles.every((r) => r.startsWith("former")) ? " (former)" : ""}`}
                  title={(t) => `${t.id}: ${t.roles.map((r) => ROLE[r]).join(", ")}`} /></>}
              {d.family?.length > 0 && <><h3>Family</h3>
                <Pills items={d.family} onOpen={onOpen} label={(f) => `${f.type.replace("_", "-")}: ${f.label}`} title={(f) => f.note || f.id} /></>}
              {d.rivals?.length > 0 && <><h3>Most frequent opponents</h3>
                <Pills items={d.rivals} onOpen={onOpen} label={(r) => `${r.label}${r.reality !== d.reality ? ` - ${r.reality}` : ""} (${fmt(r.stories)})`}
                  title={(r) => `${r.id}: on opposite sides in ${r.stories} stories`} />
                <p className="note">Stories where one is an antagonist and the other featured or supporting.</p></>}
              {d.alongside?.length > 0 && <><h3>Most often on the same side</h3>
                <Pills items={d.alongside} onOpen={onOpen} label={(r) => `${r.label}${r.reality !== d.reality ? ` - ${r.reality}` : ""} (${fmt(r.stories)})`}
                  title={(r) => `${r.id}: both featured or supporting in ${r.stories} stories`} /></>}
              {d.killed_by?.length > 0 && <><h3>Killed by</h3><Pills items={d.killed_by} onOpen={onOpen} title={(k) => k.note || k.id} /></>}
              {d.killed?.length > 0 && <><h3>Listed as the killer of ({fmt(d.killed.length)}{d.killed.length >= 40 ? "+" : ""})</h3><Pills items={d.killed} onOpen={onOpen} /></>}
              {d.variants?.length > 0 && <><h3>Variants in other realities ({fmt(d.variants_total)})</h3>
                <Pills items={d.variants} onOpen={onOpen} label={(v) => `${v.label} - ${v.reality}`} />
                {d.variants_total > d.variants.length && <p className="note">Showing the {d.variants.length} with the most appearances.</p>}</>}
              {d.events?.length > 0 && <><h3>Events</h3><Pills items={d.events} onOpen={onOpen} label={(e) => e.id} /></>}
              {d.members?.length > 0 && <><h3>Members ({fmt(d.members_total)})</h3>
                <Pills items={d.members} onOpen={onOpen} label={(m) => `${m.label}${m.roles.every((r) => r.startsWith("former")) ? " (former)" : ""}`} /></>}
              {d.allies?.length > 0 && <><h3>Listed allies</h3><Pills items={d.allies} onOpen={onOpen} /></>}
              {d.enemies?.length > 0 && <><h3>Listed enemies</h3><Pills items={d.enemies} onOpen={onOpen} /></>}
              {d.sides?.length > 0 && Object.entries(SIDE).map(([k, label]) => {
                const items = d.sides.filter((x) => x.type === k);
                return items.length ? <div key={k}><h3>{label}</h3><Pills items={items} onOpen={onOpen} /></div> : null;
              })}
              <div className="btns" style={{ marginTop: 18 }}>
                {d.kind === "character" && <>
                  <button type="button" className="btn primary" onClick={() => ask(`What is the origin of ${id}?`)}>Ask About It</button>
                  <button type="button" className="btn" onClick={() => ask(`Who are the biggest enemies of ${id}?`)}>Ask About Enemies</button></>}
                {d.kind !== "character" && d.kind !== "event" && <button type="button" className="btn primary" onClick={() => ask(`Who are the members of ${d.name}?`)}>Ask About It</button>}
                {d.kind === "event" && <button type="button" className="btn primary" onClick={() => ask(`Who fought in ${d.name}?`)}>Ask About It</button>}
              </div>
              <h3>Sources</h3>
              <ul className="sources">{d.sources.map((s) => (
                <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer">{s.label} &#8599;</a>
                  {s.permalink && <> - <a href={s.permalink} target="_blank" rel="noreferrer">revision used</a></>}</li>))}</ul>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
