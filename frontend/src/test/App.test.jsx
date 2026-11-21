import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";

const STATS = {
  total: 3, by_medium: { Comics: 2, Film: 1 }, by_kind: { numbered: 2, dimension: 1 }, by_status: { existing: 3 },
  by_type: { diverged: 1 }, listed: 2, with_page: 3, places: 0, wikidata_linked: 1, issues: 0,
  synced_at: "2026-11-21T00:00:00+00:00",
};
const ITEMS = [
  { id: "Earth-616", name: "Earth-616", kind: "numbered", types: [], status: "existing", medium: "Comics",
    first_appearance: "Marvel Comics Vol 1 1", first_year: 1939, description: "The primary continuity." },
  { id: "Earth-199999", name: "Marvel Cinematic Universe", kind: "numbered", types: [], status: "existing",
    medium: "Film", first_appearance: "Iron Man (film)", first_year: 2008, description: "The MCU." },
];
const DETAIL = {
  ...ITEMS[1], aliases: ["MCU"], creators: ["Jon Favreau"], parents: [], destroyed_by: [], children: [],
  related: [], places: [], places_total: 0, listing_kind: "numbered", medium_format: "feature film",
  medium_source: "first appearance (Film Template)", year_source: "wiki debut category",
  description_shortened: true, description_source: "page",
  sources: [{ label: "Marvel Database: Earth-199999", url: "https://marvel.fandom.com/wiki/Earth-199999",
    permalink: "https://marvel.fandom.com/wiki/Earth-199999?oldid=5" }],
};

let calls;
beforeEach(() => {
  calls = [];
  sessionStorage.setItem("atm.intro.seen", "1");
  window.history.pushState(null, "", "/");
  global.fetch = jest.fn(async (url) => {
    calls.push(url);
    const body = url.includes("/stats") ? STATS
      : url.includes("/ask/meta") ? { llm: false, examples: ["How many realities exist?"] }
        : url.includes("/characters") ? { total: 0, items: [] }
          : url.includes("/realities/") ? DETAIL
            : url.includes("/realities") ? { total: 2, items: ITEMS, facets: { medium: { Comics: 1, Film: 1 } } }
              : {};
    return { ok: true, json: async () => body };
  });
});

test("the opening sequence plays once per session and can be skipped", async () => {
  sessionStorage.removeItem("atm.intro.seen");
  jest.useFakeTimers();
  render(<App />);
  const intro = screen.getByRole("dialog", { name: "Opening sequence" });
  expect(intro).toBeInTheDocument();
  screen.getByRole("button", { name: /SKIP/ }).click();
  jest.advanceTimersByTime(1000);
  jest.useRealTimers();
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Opening sequence" })).not.toBeInTheDocument());
  expect(sessionStorage.getItem("atm.intro.seen")).toBe("1");
});

test("renders real counts, the index and the required footer", async () => {
  render(<App />);
  expect(await screen.findByText("Earth-199999")).toBeInTheDocument();
  expect(screen.getByText("2 entries match")).toBeInTheDocument();
  expect(screen.getByText(/Not affiliated with or endorsed by Marvel or Disney/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "CC BY-SA 3.0" })).toHaveAttribute("href", "https://creativecommons.org/licenses/by-sa/3.0/");
  expect(calls.every((u) => u.startsWith("/multiverse/api/v1/"))).toBe(true);
});

test("a tab filters by medium and opening a tile shows the panel with sources", async () => {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("Earth-199999");
  await user.click(screen.getByRole("button", { name: "Studios" }));
  await waitFor(() => expect(calls.some((u) => u.includes("medium=Film"))).toBe(true));
  await user.click(screen.getByRole("button", { name: /Earth-199999, Marvel Cinematic Universe/ }));
  const dialog = await screen.findByRole("dialog");
  expect(window.location.pathname).toBe("/reality/Earth-199999");
  expect(await within(dialog).findByText("Jon Favreau")).toBeInTheDocument();
  expect(within(dialog).getByText(/Shortened from the wiki/)).toBeInTheDocument();
  expect(within(dialog).getByRole("link", { name: /Marvel Database: Earth-199999/ }))
    .toHaveAttribute("href", "https://marvel.fandom.com/wiki/Earth-199999");
  expect(within(dialog).getByRole("link", { name: "revision used" })).toHaveAttribute("href", expect.stringContaining("oldid=5"));
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(window.location.pathname).toBe("/");
});

test("search is sent to the API", async () => {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("Earth-199999");
  await user.type(screen.getByRole("searchbox", { name: /Search realities/ }), "zombie");
  await waitFor(() => expect(calls.some((u) => u.includes("q=zombie"))).toBe(true));
});
