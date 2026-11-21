import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { api, askStream } from "../api/client";
import RichText from "../lib/richtext";

const STEP_ORDER = ["resolve", "plan", "query", "ground"];
const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function useTyped(text, active) {
  const [n, setN] = useState(active && !reduced() ? 0 : (text || "").length);
  useEffect(() => {
    if (!active || reduced() || !text) { setN((text || "").length); return undefined; }
    let i = 0;
    const step = Math.max(2, Math.round(text.length / 120));
    const t = setInterval(() => { i += step; setN(Math.min(i, text.length)); if (i >= text.length) clearInterval(t); }, 16);
    return () => clearInterval(t);
  }, [text, active]);
  return [text ? text.slice(0, n) : "", n < (text || "").length];
}

function BotMessage({ msg }) {
  const [shown, typing] = useTyped(msg.answer, msg.live);
  return (
    <div className="m bot" aria-live={msg.live ? "polite" : undefined}>
      <div className="who">MULTIVERSE</div>
      <ol className="steps" aria-label="Progress">
        {STEP_ORDER.filter((id) => msg.steps[id]).map((id) => {
          const s = msg.steps[id];
          return (
            <li key={id} className={`st ${s.status}`}><i aria-hidden="true" />
              <span>{s.label}{s.status === "running" ? "..." : ""}{s.detail && <small>{s.detail}</small>}</span>
            </li>
          );
        })}
      </ol>
      {msg.plan && (
        <details className="q" open={false}>
          <summary>Query plan{msg.query?.tool ? ` - ${msg.query.tool}` : ""}{msg.query ? ` - ${msg.query.rows} rows` : ""}</summary>
          <div className="code">{JSON.stringify(msg.plan, null, 1)}</div>
          {msg.query?.sql && <div className="code">{msg.query.sql}</div>}
        </details>
      )}
      {msg.error && <p className="err" role="alert">{msg.error}</p>}
      {msg.answer && <div><RichText text={shown} />{typing && <span className="caret" aria-hidden="true" />}</div>}
      {!typing && msg.citations?.length > 0 && (
        <div className="cites" aria-label="Sources">
          {msg.citations.map((c) => <a className="cite" key={c.url} href={c.url} target="_blank" rel="noreferrer">{c.label} &#8599;</a>)}
        </div>
      )}
      {!typing && msg.answer && msg.grounded === false && <p className="note">No source data matched, so no answer was given.</p>}
    </div>
  );
}

/** Multiverse Console: plain-English question -> planned query -> graph traversal -> cited answer. */
const Console = forwardRef(function Console({ onGraph }, ref) {
  const [msgs, setMsgs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [meta, setMeta] = useState(null);
  const [input, setInput] = useState("");
  const box = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { api.askMeta().then(setMeta).catch(() => setMeta({ examples: [], llm: false })); }, []);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [msgs]);

  const update = (id, fn) => setMsgs((all) => all.map((m) => (m.id === id ? fn(m) : m)));

  const ask = async (question) => {
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    const id = Date.now();
    setMsgs((all) => [...all.map((m) => ({ ...m, live: false })), { id: `${id}u`, user: q },
      { id, steps: {}, live: true, answer: "", citations: [] }]);
    try {
      await askStream(q, (ev) => {
        if (ev.type === "step") update(id, (m) => ({ ...m, steps: { ...m.steps, [ev.id]: { ...m.steps[ev.id], ...ev } },
          plan: ev.plan || m.plan }));
        else if (ev.type === "query") update(id, (m) => ({ ...m, query: ev }));
        else if (ev.type === "graph") onGraph?.(ev);
        else if (ev.type === "answer") update(id, (m) => ({ ...m, answer: ev.text, grounded: ev.grounded }));
        else if (ev.type === "citations") update(id, (m) => ({ ...m, citations: ev.items }));
      });
    } catch (e) {
      update(id, (m) => ({ ...m, error: e.status === 429 ? e.message : `The console could not answer: ${e.message}` }));
    } finally {
      setBusy(false);
    }
  };

  useImperativeHandle(ref, () => ({ ask: (q) => { inputRef.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" }); ask(q); } }));

  return (
    <div className="glass console-panel" aria-labelledby="console-h">
      <div className="hd"><span className="live" aria-hidden="true" /><h2 id="console-h" style={{ font: "inherit", margin: 0 }}>Multiverse Console</h2>
        <span className="r">{meta ? (meta.llm ? "LLM planner - grounded - cited" : "Rule planner - grounded - cited") : ""}</span></div>
      <div className="msgs" ref={box}>
        <div className="m bot"><div className="who">MULTIVERSE</div>
          Ask about any reality, character, team, rivalry, family or variant. Every answer is built only from the
          Marvel Database data and links to the pages it used. Try <b>"Who has fought both Thanos and Galactus?"</b></div>
        {msgs.map((m) => (m.user ? <div className="m user" key={m.id}>{m.user}</div> : <BotMessage key={m.id} msg={m} />))}
      </div>
      <div className="qchips" role="group" aria-label="Example questions">
        {(meta?.examples || []).map((q) => (
          <button type="button" key={q} className="chip" onClick={() => ask(q)} disabled={busy}>{q}</button>
        ))}
      </div>
      <form className="ask" onSubmit={(e) => { e.preventDefault(); ask(input); setInput(""); }}>
        <label className="sr-only" htmlFor="ask-input">Ask the multiverse</label>
        <input id="ask-input" ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)} maxLength={400}
          placeholder="Ask the multiverse..." autoComplete="off" />
        <button className="btn primary" type="submit" disabled={busy || !input.trim()}>{busy ? "..." : "Ask"}</button>
      </form>
    </div>
  );
});

export default Console;
