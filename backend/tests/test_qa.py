import json

import pytest

from app.qa import router, sqlguard, tools
from app.store import Store
from tests.conftest import P


@pytest.fixture(scope="module")
def store(data_dir):
    s = Store(data_dir)
    s.load()
    return s


@pytest.mark.parametrize("q,tool,args", [
    ("Who has fought both Thanos and Galactus?", "fought_both", {"a": "Thanos", "b": "Galactus"}),
    ("Which X-Men have also been Avengers?", "team_overlap", {"team_a": "X-Men", "team_b": "Avengers"}),
    ("Show every variant of Wolverine", "variants", {"name": "Wolverine"}),
    ("When did Spider-Man first appear?", "first_appearance", {"name": "Spider-Man"}),
    ("How many realities exist?", "count_realities", {}),
    ("How many film realities are there?", "count_realities", {"medium": "Film"}),
    ("Tell me about Earth-92131", "reality_info", {"reality": "Earth-92131"}),
    ("Who are Thor's siblings?", "relatives", {"name": "Thor", "relation": "siblings"}),
    ("Who fought in the Infinity Gauntlet?", "event_sides", {"event": "Infinity Gauntlet"}),
    ("Who created Galactus?", "creators_of", {"name": "Galactus"}),
    ("Who are the members of the Avengers?", "team_members", {"team": "Avengers", "status": "all"}),
    ("What is the origin of Spider-Man?", "origin", {"name": "Spider-Man"}),
    ("How did Hulk get his powers?", "origin", {"name": "Hulk"}),
    ("What are Thor's powers?", "origin", {"name": "Thor"}),
    ("Who killed Gwen Stacy?", "deaths", {"name": "Gwen Stacy", "direction": "victim"}),
    ("How did Gwen Stacy die?", "deaths", {"name": "Gwen Stacy", "direction": "victim"}),
    ("Who has Thanos killed?", "deaths", {"name": "Thanos", "direction": "killer"}),
    ("Are Thor and Loki enemies?", "relationship", {"a": "Thor", "b": "Loki"}),
    ("How are Wolverine and Sabretooth related?", "relationship", {"a": "Wolverine", "b": "Sabretooth"}),
    ("Magneto vs Professor X", "relationship", {"a": "Magneto", "b": "Professor X"}),
    ("When did Spider-Man first fight Venom?", "first_fight", {"a": "Spider-Man", "b": "Venom"}),
    ("Has Thor ever fought Galactus?", "first_fight", {"a": "Thor", "b": "Galactus"}),
    ("Who are Captain America's allies?", "allies", {"name": "Captain America"}),
    ("Who has Thanos fought in films?", "opponents", {"name": "Thanos", "medium": "Film"}),
    ("Who has Spider-Man fought in video games?", "opponents", {"name": "Spider-Man", "medium": "Games"}),
    ("Who is Doctor Doom's arch-enemy?", "opponents", {"name": "Doctor Doom"}),
])
def test_rule_planner(q, tool, args):
    assert router.plan(q) == (tool, args)


def test_unrelated_question_has_no_plan():
    assert router.plan("What's the box office of Endgame in yen?") is None


def test_fought_both_uses_opposing_story_roles(store):
    r = tools.run(store, "fought_both", {"a": "Thanos", "b": "Galactus"})
    ids = [x["id"] for x in r.rows]
    # Thor opposed Thanos (Infinity Gauntlet #4) and Galactus (Thor #160); the Surfer opposed Thanos but only
    # sided WITH Galactus (FF #48) or met him as a mention (Silver Surfer #50), so he is not counted.
    assert ids == ["Thor Odinson (Earth-616)"]
    assert {c["url"] for c in r.citations} >= {"https://marvel.fandom.com/wiki/Infinity_Gauntlet_Vol_1_4",
                                               "https://marvel.fandom.com/wiki/Thor_Vol_1_160"}
    assert "'Thanos (Earth-616)'" in r.sql and "Thor" in r.answer


def test_team_overlap_variants_first_appearance(store):
    r = tools.run(store, "team_overlap", {"team_a": "X-Men", "team_b": "Avengers"})
    assert {x["id"] for x in r.rows} == {"James Howlett (Earth-616)", "Henry McCoy (Earth-616)"}
    v = tools.run(store, "variants", {"name": "Spider-Man"})
    assert {x["id"] for x in v.rows} == {"Peter Parker (Earth-616)", "Peter Parker (Earth-199999)", "Peter Parker (Earth-1048)"}
    f = tools.run(store, "first_appearance", {"name": "Spider-Man"})
    assert "Amazing Fantasy Vol 1 15" in f.answer and "(1962)" in f.answer
    assert tools.run(store, "first_appearance", {"name": "Nobody Atall"}).ok is False


def test_counts_family_events_creators(store):
    c = tools.run(store, "count_realities", {})
    assert "**12**" in c.answer
    rel = tools.run(store, "relatives", {"name": "Thor", "relation": "siblings"})
    assert [x["id"] for x in rel.rows] == ["Loki Laufeyson (Earth-616)"]
    ev = tools.run(store, "event_sides", {"event": "Infinity Gauntlet"})
    assert "Thanos" in ev.answer and "Adam Warlock" in ev.answer
    assert "Stan Lee, Jack Kirby" in tools.run(store, "creators_of", {"name": "Galactus"}).answer


def test_relationship_tools(store):
    r = tools.run(store, "relationship", {"a": "Thor", "b": "Loki"})
    assert "**sibling**" in r.answer and "Killed By" in r.answer
    assert {x["kind"] for x in r.rows} >= {"relation", "opposed", "same_side"}
    f = tools.run(store, "first_fight", {"a": "Thor", "b": "Galactus"})
    assert "Thor Vol 1 160" in f.answer and "1969" in f.answer
    assert "no story" in tools.run(store, "first_fight", {"a": "Thor", "b": "Peter Parker"}).answer
    a = tools.run(store, "allies", {"name": "Thor"})
    assert {x["id"] for x in a.rows} == {"Norrin Radd (Earth-616)", "Adam Warlock (Earth-616)"}
    d = tools.run(store, "deaths", {"name": "Thor", "direction": "killer"})
    assert [x["id"] for x in d.rows] == ["Loki Laufeyson (Earth-616)"]
    o = tools.run(store, "origin", {"name": "Spider-Man"})
    assert "radioactive spider" in o.answer and "Queens" in o.answer and "Spider-Physiology" in o.answer
    with pytest.raises(ValueError):
        tools.run(store, "opponents", {"name": "Thanos", "medium": "Opera"})


@pytest.mark.parametrize("sql", [
    "DELETE FROM characters", "SELECT * FROM read_csv('/etc/passwd')", "SELECT getenv('HOME')",
    "SELECT 1; SELECT 2", "SELECT * FROM information_schema.tables", "SELECT * FROM sync_runs",
    "SELECT * FROM duckdb_settings()", "ATTACH 'x.db'",
])
def test_sql_guard_rejects(store, sql):
    cur = store.cursor()
    with pytest.raises(sqlguard.UnsafeQuery):
        sqlguard.validate(cur, sql)


def test_sql_guard_allows_ctes_and_limits(store):
    cur = store.cursor()
    rows = sqlguard.run(cur, "WITH t AS (SELECT id FROM characters) SELECT count(*) AS n FROM t")
    assert rows == [{"n": 14}]
    assert sqlguard.validate(cur, "SELECT id FROM characters").endswith("LIMIT 200")


def _events(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def test_ask_streams_steps_query_answer_and_citations(client):
    from app.api import ask
    ask.visitor_limit.reset(); ask.global_limit.reset()
    resp = client.post(f"{P}/ask", json={"question": "Who has fought both Thanos and Galactus?"})
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
    evs = _events(resp)
    kinds = [e["type"] for e in evs]
    assert kinds[0] == "step" and kinds[-1] == "done" and evs[-1]["ok"]
    plan = next(e for e in evs if e["type"] == "step" and e.get("plan"))
    assert plan["plan"] == {"tool": "fought_both", "args": {"a": "Thanos", "b": "Galactus"}}
    assert "planner: rules" in plan["detail"]
    assert "FROM appearances" in next(e for e in evs if e["type"] == "query")["sql"]
    assert "Thor" in next(e for e in evs if e["type"] == "answer")["text"]
    assert next(e for e in evs if e["type"] == "citations")["items"]
    assert "__session" in resp.cookies


def test_ask_says_plainly_when_data_cannot_answer(client):
    from app.api import ask
    ask.visitor_limit.reset(); ask.global_limit.reset()
    evs = _events(client.post(f"{P}/ask", json={"question": "What is Thanos's favourite colour?"}))
    ans = next(e for e in evs if e["type"] == "answer")
    assert ans["grounded"] is False and "can't" in ans["text"]


def test_ask_rate_limit(client):
    from app.api import ask
    ask.visitor_limit.reset(); ask.global_limit.reset()
    codes = [client.post(f"{P}/ask", json={"question": f"How many realities exist? {i}"}).status_code for i in range(9)]
    assert 429 in codes and codes[0] == 200
    ask.visitor_limit.reset(); ask.global_limit.reset()


def test_entity_panel_and_neighbourhood(client):
    thor = client.get(f"{P}/entities/Thor Odinson (Earth-616)").json()
    assert thor["kind"] == "character" and thor["teams"][0]["id"] == "Avengers (Earth-616)"
    assert thor["family"][0]["id"] == "Loki Laufeyson (Earth-616)"
    assert thor["sources"][0]["url"].startswith("https://marvel.fandom.com/wiki/")
    g = client.get(f"{P}/graph/neighbourhood", params={"node": "Thanos (Earth-616)"}).json()
    kinds = {(e["b"], e["kind"]) for e in g["edges"]}
    assert ("Thor Odinson (Earth-616)", "enemy") in kinds and ("Avengers (Earth-616)", "enemy") in kinds
    assert client.get(f"{P}/search", params={"q": "galac"}).json()["items"][0]["id"] == "Galan (Earth-616)"
    # alias matches count too, and paging covers every match
    logan = client.get(f"{P}/search", params={"q": "logan", "kinds": "character"}).json()
    assert logan["total"] == 1 and logan["items"][0]["id"] == "James Howlett (Earth-616)"
    parker = [client.get(f"{P}/search", params={"q": "parker", "kinds": "character", "limit": 2, "offset": o}).json() for o in (0, 2)]
    assert parker[0]["total"] == 3 and len(parker[0]["items"]) + len(parker[1]["items"]) == 3
    loki = client.get(f"{P}/entities/Loki Laufeyson (Earth-616)").json()
    assert loki["killed_by"][0]["id"] == "Thor Odinson (Earth-616)" and "rivals" in loki and "alongside" in loki
    peter = client.get(f"{P}/entities/Peter Parker (Earth-616)").json()
    assert peter["origin"].startswith("Human") and peter["powers"] == ["Spider-Physiology"]
    stats = client.get(f"{P}/stats").json()
    assert stats["graph"]["characters"] == 14 and stats["graph"]["by_relation"]["member"] >= 1


def test_mcu_timeline_links_exact_titles_and_reports_the_rest(client):
    t = client.get(f"{P}/timeline/earth-199999").json()
    one = t["phases"][0]
    assert one["phase"] == "Phase One" and one["saga"] == "The Infinity Saga"
    assert (one["start_year"], one["end_year"]) == (2008, 2012) and one["permalink"].endswith("?oldid=2618181")
    by = {e["title"]: e for e in one["entries"]}
    assert by["Iron Man"]["work"] == "Iron Man (film)" and by["Iron Man"]["year"] == 2008
    assert by["Iron Man"]["match"] == "exact title"
    assert by["The Avengers"]["work"] is None and by["The Consultant"]["kind"] == "one-shot"
    assert (t["linked"], t["total"]) == (1, 3)


def test_who_appears_lists_roles_and_falls_back_to_teams(store):
    assert router.plan("Who appears in Fantastic Four Vol 1 48?") == ("who_appears", {"work": "Fantastic Four Vol 1 48"})
    assert router.plan("Who are the villains in Thor Vol 1 160?") == ("who_appears", {"work": "Thor Vol 1 160", "role": "villains"})
    r = tools.run(store, "who_appears", {"work": "Fantastic Four Vol 1 48", "role": "villains"})
    assert {x["id"] for x in r.rows} == {"Galan (Earth-616)", "Norrin Radd (Earth-616)"} and "Antagonists" in r.answer
    assert tools.run(store, "who_appears", {"work": "X-Men"}).tool == "team_members"
    assert tools.run(store, "who_appears", {"work": "No Such Story"}).ok is False
