import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Console from "../components/Console";

const EVENTS = [
  { type: "step", id: "resolve", label: "Resolving names across realities", status: "running" },
  { type: "step", id: "resolve", status: "done", detail: "thanos -> Thanos (Earth-616)" },
  { type: "step", id: "plan", label: "Planning the query", status: "running" },
  { type: "step", id: "plan", status: "done", detail: "planner: groq", plan: { tool: "fought_both", args: { a: "Thanos", b: "Galactus" } } },
  { type: "query", sql: "WITH opp_a AS (SELECT ... FROM appearances ...)", tool: "fought_both", rows: 1 },
  { type: "graph", nodes: ["Thanos (Earth-616)", "Galan (Earth-616)"], edges: [], kind: "enemy" },
  { type: "answer", text: "Characters who opposed both:\n- **Silver Surfer (Norrin Radd, Earth-616)** - 25 stories", grounded: true },
  { type: "citations", items: [{ label: "Marvel Database: Annihilation Vol 1 1", url: "https://marvel.fandom.com/wiki/Annihilation_Vol_1_1" }] },
  { type: "done", ok: true },
];

test("asks, shows progress, the plan and query, a typed answer and source links", async () => {
  window.matchMedia = () => ({ matches: true }); // reduced motion: no typing delay
  const graphs = [];
  global.fetch = jest.fn(async (url, opts) => {
    if (url.endsWith("/ask/meta")) return { ok: true, json: async () => ({ llm: true, examples: ["Who has fought both Thanos and Galactus?"] }) };
    expect(JSON.parse(opts.body)).toEqual({ question: "Who has fought both Thanos and Galactus?" });
    return { ok: true, text: async () => EVENTS.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("") };
  });
  render(<Console onGraph={(g) => graphs.push(g)} />);
  await userEvent.click(await screen.findByRole("button", { name: "Who has fought both Thanos and Galactus?" }));
  expect(await screen.findByText("Silver Surfer (Norrin Radd, Earth-616)")).toBeInTheDocument();
  expect(screen.getByText("LLM planner - grounded - cited")).toBeInTheDocument();
  expect(screen.getByText(/planner: groq/)).toBeInTheDocument();
  expect(screen.getByText(/FROM appearances/)).toBeInTheDocument();
  const sources = screen.getByLabelText("Sources");
  expect(within(sources).getByRole("link")).toHaveAttribute("href", "https://marvel.fandom.com/wiki/Annihilation_Vol_1_1");
  await waitFor(() => expect(graphs[0].kind).toBe("enemy"));
});

test("shows the rate-limit message from the API", async () => {
  global.fetch = jest.fn(async (url) => (url.endsWith("/ask/meta")
    ? { ok: true, json: async () => ({ llm: false, examples: [] }) }
    : { ok: false, status: 429, statusText: "Too Many Requests", json: async () => ({ detail: "You're asking faster than the console allows." }) }));
  render(<Console />);
  await userEvent.type(screen.getByLabelText("Ask the multiverse"), "How many realities exist?{enter}");
  expect(await screen.findByRole("alert")).toHaveTextContent("asking faster");
});
