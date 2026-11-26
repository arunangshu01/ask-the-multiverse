import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import IndexGrid from "../components/IndexGrid";

const page = (offset, n) => Array.from({ length: n }, (_, i) => ({
  id: `Earth-${offset + i + 1}`, name: null, kind: "numbered", medium: "Comics", status: "existing", description: "d",
}));

test("pages load only on request, with a count, so the footer below stays reachable", async () => {
  const calls = [];
  global.fetch = jest.fn(async (url) => {
    const offset = Number(new URL(url, "http://x").searchParams.get("offset") || 0);
    calls.push(offset);
    return { ok: true, json: async () => ({ total: 70, items: page(offset, offset ? 10 : 60), facets: { medium: { Comics: 70 } } }) };
  });
  render(<IndexGrid query="" onOpen={() => {}} mediumFilter="all" setMediumFilter={() => {}} />);
  expect(await screen.findByText("Showing 60 of 70")).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: /^Earth-\d+:/ })).toHaveLength(60);
  expect(calls).toEqual([0]); // nothing loads by itself
  await userEvent.click(screen.getByRole("button", { name: "Load 10 more" }));
  await waitFor(() => expect(screen.getByText("All 70 shown")).toBeInTheDocument());
  expect(screen.getAllByRole("button", { name: /^Earth-\d+:/ })).toHaveLength(70);
  expect(calls).toEqual([0, 60]);
});
