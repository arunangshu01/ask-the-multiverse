import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Graph from "../components/Graph";

const doom = (n) => ({ id: `Victor von Doom (Earth-${n})`, kind: "character", label: "Doctor Doom", reality: `Earth-${n}`, appearances: 100 - n });

test("search lists every match across realities and pages in the rest", async () => {
  window.matchMedia = () => ({ matches: true });
  const searches = [];
  global.fetch = jest.fn(async (url) => {
    if (url.includes("/graph/neighbourhood")) return { ok: true, json: async () => ({ center: "Thanos (Earth-616)", nodes: [], edges: [] }) };
    const qs = new URL(url, "http://x").searchParams;
    searches.push(Object.fromEntries(qs));
    const offset = Number(qs.get("offset") || 0);
    const items = offset ? [doom(41), doom(42)] : Array.from({ length: 40 }, (_, i) => doom(i + 1));
    return { ok: true, json: async () => ({ items, total: 42, offset }) };
  });
  render(<Graph center="Thanos (Earth-616)" />);
  await userEvent.type(screen.getByPlaceholderText("Find a character..."), "doom");
  expect(await screen.findByText("42 matches across all realities")).toBeInTheDocument();
  expect(searches[0]).toMatchObject({ q: "doom", kinds: "character,team,organization,event", limit: "40" });
  const matches = () => within(screen.getByRole("group", { name: "Matches across all realities" })).getAllByRole("button", { name: /Doctor Doom/ });
  expect(matches()).toHaveLength(40);
  await userEvent.click(screen.getByRole("button", { name: "Show more (2 left)" }));
  await waitFor(() => expect(matches()).toHaveLength(42));
  expect(searches.at(-1)).toMatchObject({ offset: "40" });
});
