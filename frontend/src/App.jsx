import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import EntityPanel from "./components/EntityPanel";
import Footer from "./components/Footer";
import Intro, { shouldPlayIntro } from "./components/Intro";
import RealityPanel from "./components/RealityPanel";
import TopBar from "./components/TopBar";
import { DIVISIONS, MEDIA } from "./lib/media";
import { ROUTES, navigate, parsePath, usePath } from "./lib/router";
import Coverage from "./pages/Coverage";
import Credits from "./pages/Credits";
import Home from "./pages/Home";

export default function App() {
  const path = usePath();
  const route = parsePath(path);
  const [division, setDivision] = useState("all");
  const [mediumFilter, setMediumFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [stats, setStats] = useState(null);
  const [statsError, setStatsError] = useState(null);
  const [intro, setIntro] = useState(() => shouldPlayIntro());
  const sweep = useRef(null);
  const consoleRef = useRef(null);

  useEffect(() => {
    api.stats().then(setStats).catch((e) => setStatsError(e.message));
  }, []);

  const div = DIVISIONS.find((d) => d.key === division);
  useEffect(() => {
    const m = MEDIA[div.accent];
    document.documentElement.style.setProperty("--accent", m.color);
    document.documentElement.style.setProperty("--accent-glow", m.glow);
  }, [div]);

  const chooseDivision = (key) => {
    setDivision(key);
    setMediumFilter("all");
    const el = sweep.current;
    if (el) { el.classList.remove("go"); void el.offsetWidth; el.classList.add("go"); }
    if (route.page !== "home") navigate(ROUTES.home);
  };
  const onQuery = (q) => {
    setQuery(q);
    if (route.page !== "home") navigate(ROUTES.home);
  };
  const openReality = useCallback((id, opts) => navigate(ROUTES.reality(id), { keepScroll: true, ...opts }), []);
  const openEntity = useCallback((id) => navigate(ROUTES.entity(id), { keepScroll: true }), []);
  const closePanel = useCallback(() => navigate(ROUTES.home, { keepScroll: true }), []);
  const askFromPanel = useCallback((q) => {
    setTimeout(() => {
      document.getElementById("console")?.scrollIntoView({ behavior: "smooth", block: "start" });
      consoleRef.current?.ask(q);
    }, 50);
  }, []);
  const replay = useCallback(() => {
    try { sessionStorage.removeItem("atm.intro.seen"); } catch { /* private mode */ }
    if (!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) setIntro(true);
  }, []);

  return (
    <>
      {intro && <Intro onDone={() => setIntro(false)} />}
      <div className="grain" aria-hidden="true" /><div className="vignette" aria-hidden="true" />
      <div className="sweep" ref={sweep} aria-hidden="true" />
      <a className="sr-only" href="#console">Skip to the Multiverse Console</a>
      <TopBar division={division} onDivision={chooseDivision} query={query} onQuery={onQuery} page={route.page} onReplay={replay} />
      <main>
        {statsError && <section><p className="err" role="alert">The index is unavailable right now: {statsError}</p></section>}
        {route.page === "home" && (
          <Home stats={stats} query={query} media={div.media} mediumFilter={mediumFilter} setMediumFilter={setMediumFilter}
            onOpen={openReality} onEntity={openEntity} consoleRef={consoleRef} />
        )}
        {route.page === "coverage" && <Coverage stats={stats} />}
        {route.page === "credits" && <Credits />}
      </main>
      <Footer syncedAt={stats?.synced_at} />
      {route.reality && <RealityPanel id={route.reality} onClose={closePanel} onOpen={openReality} onEntity={openEntity} onAsk={askFromPanel} />}
      {route.entity && <EntityPanel id={route.entity} onClose={closePanel} onOpen={openEntity} onReality={openReality} onAsk={askFromPanel} />}
    </>
  );
}
