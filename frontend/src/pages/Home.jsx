import { useRef, useState } from "react";
import Console from "../components/Console";
import Graph from "../components/Graph";
import Hero from "../components/Hero";
import IndexGrid from "../components/IndexGrid";
import PosterRows from "../components/PosterRows";
import Timeline from "../components/Timeline";
import { MEDIA, fmt } from "../lib/media";

function StatsStrip({ stats, onMedium }) {
  if (!stats) return null;
  const items = [["Entries", stats.total, "all"], ...Object.keys(MEDIA).filter((k) => stats.by_medium[k])
    .map((k) => [MEDIA[k].label, stats.by_medium[k], k])];
  const g = stats.graph || {};
  const extra = [["Dimensions", stats.by_kind.dimension], ["Realms", stats.by_kind.realm], ["Characters", g.characters],
    ["Teams & orgs", g.teams], ["Events", g.events], ["Relationships", g.relations], ["Story appearances", g.appearances],
    ["Creators", g.creators]].filter(([, n]) => n);
  return (
    <section aria-labelledby="stats-h">
      <div className="sh"><h2 id="stats-h">Multiverse Index</h2>
        <span className="c">Real counts from the Marvel Database. Select a medium to browse it.</span></div>
      <div className="stats">
        {items.map(([label, n, key]) => (
          <button type="button" className="stat" key={key} onClick={() => onMedium(key)}>
            <div className="n">{fmt(n)}</div><div className="l">{label}</div>
          </button>
        ))}
        {extra.map(([l, n]) => <div className="stat" key={l}><div className="n">{fmt(n)}</div><div className="l">{l}</div></div>)}
      </div>
    </section>
  );
}

export default function Home({ stats, query, media, mediumFilter, setMediumFilter, onOpen, onEntity, consoleRef }) {
  const [highlight, setHighlight] = useState(null);
  const pick = (k) => {
    setMediumFilter(k);
    document.getElementById("index")?.scrollIntoView({ behavior: "smooth" });
  };
  const ask = (q) => {
    document.getElementById("console")?.scrollIntoView({ behavior: "smooth", block: "start" });
    consoleRef.current?.ask(q);
  };
  const hasGraph = Boolean(stats?.graph?.characters);
  return (
    <>
      <Hero onExplore={onOpen} onAsk={ask} />
      <section id="console" aria-label="Ask the multiverse">
        <div className="split">
          <Console ref={consoleRef} onGraph={(g) => g.nodes?.length && setHighlight({ ...g, at: Date.now() })} />
          {hasGraph ? <Graph center="Thanos (Earth-616)" highlight={highlight} onOpen={onEntity} />
            : <div className="glass"><div className="gempty">The connections graph appears once the character index is loaded.</div></div>}
        </div>
      </section>
      <PosterRows media={media} onOpen={onOpen} onSeeAll={pick} />
      {hasGraph && <Timeline onAsk={ask} onReality={onOpen} />}
      <StatsStrip stats={stats} onMedium={pick} />
      <IndexGrid query={query} media={media} onOpen={onOpen} mediumFilter={mediumFilter}
        setMediumFilter={setMediumFilter} types={stats ? Object.keys(stats.by_type) : null} />
    </>
  );
}
