from ingest import media


def page(title, text, cats=()):
    return {"title": title, "revisions": [{"slots": {"main": {"content": text}}}],
            "categories": [{"title": f"Category:{c}"} for c in cats]}


FILM = "{{Marvel Database:Film Template\n| Type = Feature Film\n| Release Date = April 30, 2008\n| IMDB ID = tt0371746\n}}"
EPISODE = "{{Marvel Database:Episode Template\n| Year = 1992\n| Month = October\n}}"
SERIES_ANIM = "{{Marvel Database:Television Series Template\n| SeriesType = Animated; TV\n}}"
SERIES_LIVE = "{{Marvel Database:Television Series Template\n| SeriesType = Live Action; TV; Web\n}}"


def test_film_live_action_and_animated():
    iron = media.classify_work(page("Iron Man (film)", FILM), {}, set())
    assert (iron["medium"], iron["format"], iron["year"]) == ("Film", "feature film", 2008)
    verse = media.classify_work(page("Spider-Man: Into the Spider-Verse", FILM), {},
                                {"Spider-Man: Into the Spider-Verse"})
    assert verse["medium"] == "Animation" and verse["format"] == "animated feature film"


def test_episode_medium_comes_from_its_series():
    ep = page("X-Men: The Animated Series Season 1 1", EPISODE, ["Episodes", "X-Men: The Animated Series Season 1"])
    series = {"X-Men: The Animated Series": page("X-Men: The Animated Series", SERIES_ANIM, ["Animated Series"])}
    out = media.classify_work(ep, series, set())
    assert (out["medium"], out["year"], out["series"]) == ("Animation", 1992, "X-Men: The Animated Series")
    loki = page("Loki (TV series) Season 1 1", EPISODE, ["Loki (TV series) Season 1"])
    out = media.classify_work(loki, {"Loki (TV series)": page("Loki (TV series)", SERIES_LIVE)}, set())
    assert out["medium"] == "Television"
    assert media.classify_work(loki, {}, set())["medium"] is None


def test_comic_novel_game_and_unknown():
    comic = page("Fantastic Four Vol 1 48", "{{Marvel Database:Comic Template\n| Year = 1966\n}}")
    out = media.classify_work(comic, {}, set())
    assert (out["medium"], out["year"]) == ("Comics", 1966)
    novel = page("Hostile Takeover", "{{Marvel Database:Novel Template\n| Release Date = August 21, 2018\n}}")
    assert media.classify_work(novel, {}, set())["medium"] == "Prose"
    game = page("LEGO Marvel Super Heroes", "{{Marvel Database:Video Game Template\n}}", ["2013, October"])
    out = media.classify_work(game, {}, set())
    assert (out["medium"], out["year"]) == ("Games", 2013)
    event = page("Secret Wars (2015 Event)", "{{Marvel Database:Event Template\n}}")
    out = media.classify_work(event, {}, set())
    assert out["medium"] is None and "Event Template" in out["reason"]
    missing = {"title": "Nope", "missing": True}
    assert media.classify_work(missing, {}, set())["reason"] == "first-appearance page missing"


def test_external_links_only_classify_comic_issues():
    assert media.classify_external({"target": "Tom Strong Vol 1 1", "external": "dc"})["medium"] == "Comics"
    assert media.classify_external({"target": "Some Website", "external": "wikipedia"})["medium"] is None
