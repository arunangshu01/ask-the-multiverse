import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Coverage from "../pages/Coverage";

const STATS = {
  total: 10, listed: 8, with_page: 7, places: 2, wikidata_linked: 1, issues: 3, synced_at: "2026-11-21T00:00:00+00:00",
  by_medium: { Comics: 9, Film: 1 }, by_kind: { numbered: 10 }, by_status: { existing: 10 }, by_type: { diverged: 2 },
};
const COV = {
  run: { meta: { listing: { official_rows: 7, trn_rows: 1 }, api_calls: 12, cache_hits: 3 } },
  checks: [{ check: "golden realities keep their medium", status: "pass", detail: "{}" }],
  summary: [{ stage: "classify", reason: "rejected: character page", n: 3 }],
  total: 3,
  items: [{ page: "Peter Parker (Earth-616)", stage: "classify", reason: "rejected: character page", detail: "Character Template" }],
  overrides: [{ id: "Earth-1048", medium: "Games", medium_source: "reviewed override (tie-in novel)" }],
  keyword_classified: 0, known_gaps: ["Characters are not ingested yet."],
};

test("shows real counts, checks, rejected pages with source links and filters", async () => {
  const calls = [];
  global.fetch = jest.fn(async (url) => { calls.push(url); return { ok: true, json: async () => COV }; });
  render(<Coverage stats={STATS} />);
  expect(await screen.findByText("golden realities keep their medium")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Peter Parker (Earth-616)" }))
    .toHaveAttribute("href", "https://marvel.fandom.com/wiki/Peter_Parker_(Earth-616)");
  expect(screen.getByText("Earth-1048")).toBeInTheDocument();
  expect(screen.getByText("Characters are not ingested yet.")).toBeInTheDocument();
  await userEvent.type(screen.getByRole("searchbox", { name: "Search pages" }), "Parker");
  await waitFor(() => expect(calls.some((u) => u.includes("q=Parker"))).toBe(true));
});
