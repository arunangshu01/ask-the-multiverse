import { useEffect, useState } from "react";
import { api } from "../api/client";
import { DISCLAIMER } from "../components/Footer";

export default function Credits() {
  const [c, setC] = useState(null);
  useEffect(() => { api.credits().then(setC).catch(() => setC(null)); }, []);
  return (
    <section aria-labelledby="cr-h">
      <div className="sh"><h1 id="cr-h">Credits and licences</h1></div>
      <p className="lede">{DISCLAIMER}</p>
      <div className="panel">
        <h2>Data</h2>
        <p className="lede">
          The data is derived from the <a href="https://marvel.fandom.com/" target="_blank" rel="noreferrer">Marvel Database</a>,
          written by its contributors on Fandom and licensed under{" "}
          <a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noreferrer">CC BY-SA 3.0 (Unported)</a>,
          as stated on the wiki's <a href="https://marvel.fandom.com/wiki/Marvel_Database:Copyrights" target="_blank" rel="noreferrer">copyright page</a>.
          Our cleaned dataset is shared under the same licence. Descriptions may be shortened; every entry links to the exact
          wiki page (and revision) it was taken from. Wiki images are not used.
        </p>
        <p className="lede">Cross-links and animated-film flags come from <a href="https://www.wikidata.org/" target="_blank" rel="noreferrer">Wikidata</a> (CC0).</p>
        {c && (
          <table className="tbl"><thead><tr><th>Source</th><th>Licence</th><th>Used for</th></tr></thead><tbody>
            {c.sources.map((s) => (
              <tr key={s.name}><td><a href={s.url} target="_blank" rel="noreferrer">{s.name}</a></td>
                <td><a href={s.licence_url} target="_blank" rel="noreferrer">{s.licence}</a></td><td>{s.used_for}</td></tr>))}
          </tbody></table>
        )}
      </div>
      <div className="panel">
        <h2>Code and artwork</h2>
        <p className="lede">The code is MIT-licensed (<a href="https://github.com/arunangshu01/ask-the-multiverse" target="_blank" rel="noreferrer">GitHub</a>).
          All artwork on this site is generated from each entry's name; no logos, film stills, official artwork or wiki images are used.
          This is a non-commercial fan project with no ads or paid tiers.</p>
      </div>
    </section>
  );
}
