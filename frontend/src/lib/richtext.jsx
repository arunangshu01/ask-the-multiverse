// Minimal, safe renderer for answers: **bold**, "- " bullet lists and paragraphs. No HTML is
// ever injected; everything becomes React text nodes.

function inline(text, key) {
  const out = [];
  text.split(/(\*\*[^*]+\*\*)/g).forEach((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) out.push(<strong key={`${key}-${i}`}>{part.slice(2, -2)}</strong>);
    else if (part) out.push(part);
  });
  return out;
}

export default function RichText({ text }) {
  const blocks = [];
  let list = null;
  (text || "").split("\n").forEach((line, i) => {
    const m = line.match(/^\s*[-*]\s+(.*)$/);
    if (m) {
      if (!list) { list = []; blocks.push({ list }); }
      list.push(inline(m[1], i));
    } else {
      list = null;
      if (line.trim()) blocks.push({ p: inline(line, i) });
    }
  });
  return blocks.map((b, i) => (b.list
    ? <ul key={i}>{b.list.map((li, j) => <li key={j}>{li}</li>)}</ul>
    : <p key={i}>{b.p}</p>));
}
