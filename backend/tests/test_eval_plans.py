"""CI part of the evaluation set: every question must be planned onto its expected tool by the
rule planner (answer accuracy needs the data snapshot: `python -m eval.run`)."""

import pytest

from app.qa import router
from eval.run import load

CASES = load()


def test_eval_set_size():
    assert len(CASES) >= 50


@pytest.mark.parametrize("case", CASES, ids=[c["q"] for c in CASES])
def test_rule_plan_matches_expected_tool(case):
    planned = router.plan(case["q"])
    assert (planned[0] if planned else None) == case["tool"]
