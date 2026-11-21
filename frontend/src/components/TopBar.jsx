import { DIVISIONS } from "../lib/media";
import { ROUTES, linkTo } from "../lib/router";

export default function TopBar({ division, onDivision, query, onQuery, page, onReplay }) {
  const home = linkTo(ROUTES.home);
  return (
    <header className="topbar">
      <a className="logo" href={home.href} title="Home - click again to replay the opening"
        onClick={(e) => { if (window.location.pathname === "/" && !e.metaKey && !e.ctrlKey) { e.preventDefault(); onReplay?.(); } else home.onClick(e); }}
        aria-label="Ask the Multiverse home">Ask the Multiverse</a>
      <nav aria-label="Media">
        <ul className="divs">
          {DIVISIONS.map((d) => (
            <li key={d.key}>
              <button type="button" className="div" aria-pressed={page === "home" && division === d.key}
                onClick={() => onDivision(d.key)}>{d.label}</button>
            </li>
          ))}
        </ul>
      </nav>
      <div className="nav-r">
        <label className="search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9a9aa6" strokeWidth="2" aria-hidden="true">
            <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
          </svg>
          <span className="sr-only">Search realities, dimensions and realms</span>
          <input type="search" value={query} onChange={(e) => onQuery(e.target.value)}
            placeholder="Search realities, dimensions, realms..." />
        </label>
        <a className="navlink" {...linkTo(ROUTES.coverage)} aria-current={page === "coverage" ? "page" : undefined}>Coverage</a>
        <a className="navlink" {...linkTo(ROUTES.credits)} aria-current={page === "credits" ? "page" : undefined}>Credits</a>
        <button type="button" className="ghostbtn" onClick={onReplay} aria-label="Replay the opening sequence">&#8635; OPENING</button>
      </div>
    </header>
  );
}
