import CreatorMark from "./CreatorMark";
import { ROUTES, linkTo } from "../lib/router";

export const DISCLAIMER = "Fan-made project. Not affiliated with or endorsed by Marvel or Disney. "
  + "All characters and related names are trademarks of their respective owners.";

export default function Footer({ syncedAt }) {
  return (
    <footer className="foot">
      <div>{DISCLAIMER}</div>
      <div>
        Data from the <a href="https://marvel.fandom.com/" target="_blank" rel="noreferrer">Marvel Database</a> contributors
        on Fandom, licensed under <a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noreferrer">CC BY-SA 3.0</a>{" "}
        (<a href="https://marvel.fandom.com/wiki/Marvel_Database:Copyrights" target="_blank" rel="noreferrer">wiki licence</a>);
        descriptions may be shortened. MCU phases from the <a href="https://marvelcinematicuniverse.fandom.com/" target="_blank" rel="noreferrer">MCU Wiki</a> contributors
        on Fandom (<a href="https://www.fandom.com/licensing" target="_blank" rel="noreferrer">CC BY-SA</a>). Cross-links from <a href="https://www.wikidata.org/" target="_blank" rel="noreferrer">Wikidata</a> (CC0).
        {" "}<a {...linkTo(ROUTES.credits)}>Credits</a> - <a {...linkTo(ROUTES.coverage)}>Coverage</a>
        {syncedAt ? ` - last synced ${new Date(syncedAt).toUTCString().replace(" GMT", " UTC")}` : ""}
      </div>
      <div>Code: MIT. Non-commercial: no ads, no paid tiers.</div>
      <CreatorMark variant="card" />
    </footer>
  );
}
