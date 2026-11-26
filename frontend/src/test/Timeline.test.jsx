import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Timeline from "../components/Timeline";

const entry = (title, work, extra = {}) => ({ position: 1, kind: "film", title, season: null, year: work ? 2008 : null, work,
  work_url: work ? `https://marvel.fandom.com/wiki/${work}` : null, mcu_url: `https://marvelcinematicuniverse.fandom.com/wiki/${title}`, ...extra });

test("shows each phase with linked and unlinked titles", async () => {
  global.fetch = jest.fn(async () => ({ ok: true, json: async () => ({
    linked: 1, total: 3, phases: [
      { phase: "Phase One", saga: "The Infinity Saga", start_year: 2008, end_year: 2012, url: "u1", permalink: "u1?oldid=1",
        entries: [entry("Iron Man", "Iron Man (film)"), { ...entry("The Avengers", null), position: 2 }] },
      { phase: "Phase Two", saga: "The Infinity Saga", start_year: 2013, end_year: 2015, url: "u2", permalink: null,
        entries: [entry("Iron Man 3", "Iron Man 3 (film)", { year: 2013 })] },
    ] }) }));
  const asks = [];
  render(<Timeline onAsk={(q) => asks.push(q)} />);
  expect(await screen.findByText("Iron Man")).toBeInTheDocument();
  expect(screen.getByText(/1 of 3 titles linked/)).toBeInTheDocument();
  expect(screen.getByText("not linked")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  expect(asks).toEqual(["Who appears in Iron Man (film)?"]);
  await userEvent.click(screen.getByRole("tab", { name: /Two/ }));
  expect(screen.getByText("Iron Man 3")).toBeInTheDocument();
});
