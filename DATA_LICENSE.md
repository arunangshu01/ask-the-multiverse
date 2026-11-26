# Data licence

The **code** in this repository is licensed under the MIT licence (`LICENSE`).

The **data** shown by Ask the Multiverse, and any dataset this project produces (the Parquet and DuckDB
files written by `python -m ingest`), is derived from third-party sources and keeps their terms:

| Source | Licence | What we use |
| --- | --- | --- |
| [Marvel Database](https://marvel.fandom.com/) on Fandom, by its contributors | [CC BY-SA 3.0 Unported](https://creativecommons.org/licenses/by-sa/3.0/), as stated on the wiki's [copyright page](https://marvel.fandom.com/wiki/Marvel_Database:Copyrights) | reality, dimension and realm pages, the reality listings, character, team and event pages (profiles, relationships), story appearance lists, first appearances, creators, descriptions |
| [MCU Wiki](https://marvelcinematicuniverse.fandom.com/) on Fandom, by its contributors | CC BY-SA, as reported by the wiki's API and [Fandom's licensing page](https://www.fandom.com/licensing) | which films, series, specials and one-shots belong to each MCU phase |
| [Wikidata](https://www.wikidata.org/) | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | cross-links to Marvel Database pages (P6262), animated-film flags via IMDb IDs (P345) |

Because the Marvel Database and MCU Wiki text is CC BY-SA, **our derived data is also licensed under CC BY-SA 3.0**.
If you reuse it, credit "Marvel Database contributors on Fandom" with a link to the source page, and share
your adaptation under the same licence.

- Descriptions are taken from the wiki's own text and may be shortened; each record links to the full page
  and to the exact revision used (`?oldid=`).
- Wiki images are **not** copied or shown: images on Fandom are not covered by the text licence.
- Character names and related marks are trademarks of their respective owners. This is a non-commercial fan
  project, not affiliated with or endorsed by Marvel or Disney.
