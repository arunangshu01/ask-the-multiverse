import { useEffect, useState } from "react";

// Minimal path router, same approach as Flowbench. Firebase Hosting and the
// Vite dev server both fall back to index.html, so deep links work on refresh.

export const ROUTES = {
  home: "/",
  coverage: "/coverage",
  credits: "/credits",
  reality: (id) => `/reality/${encodeURIComponent(id)}`,
  entity: (id) => `/entity/${encodeURIComponent(id)}`,
};

export function navigate(to, { replace = false, keepScroll = false } = {}) {
  if (to === window.location.pathname + window.location.search) return;
  window.history[replace ? "replaceState" : "pushState"](null, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
  if (!keepScroll) window.scrollTo(0, 0);
}

export function usePath() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  return path;
}

export function parsePath(path) {
  const m = path.match(/^\/reality\/(.+)$/);
  if (m) return { page: "home", reality: decodeURIComponent(m[1]) };
  const e = path.match(/^\/entity\/(.+)$/);
  if (e) return { page: "home", entity: decodeURIComponent(e[1]) };
  if (path === ROUTES.coverage) return { page: "coverage" };
  if (path === ROUTES.credits) return { page: "credits" };
  return { page: "home" };
}

/** Props for <a>: client-side navigation, but modifier-clicks still open new tabs. */
export function linkTo(to, opts) {
  return {
    href: to,
    onClick: (e) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      navigate(to, opts);
    },
  };
}
