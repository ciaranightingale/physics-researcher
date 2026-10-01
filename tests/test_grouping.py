"""Headline grouping, pinned to real headline pairs taken from the live feeds on 2026-10-01.

What the headline path actually does on these feeds is de-duplicate one outlet against itself: BBC
and Physics World both republish the same headline, and those pairs share 4-10 content words. No
cross-source merge fired in any window from 7 to 30 days, so the pairs below are the real
behaviour, not a sample of cross-outlet matching. Shared coverage is found by DOI/arXiv instead.

Moving MIN_OVERLAP or MIN_SHARED_WORDS should break this file rather than quietly change what the
server merges.
"""

import pytest

from science_scout.grouping import group_items
from science_scout.models import Item

# One outlet, same story posted twice. These are what the headline path exists to catch.
SAME_OUTLET_DUPLICATES = [
    pytest.param(
        ("bbc-science", "Swiss glaciers suffer 'disastrous' year of ice loss, threatening water supplies"),
        ("bbc-science", "Swiss glaciers suffer 'disastrous' year of ice loss, threatening water supplies"),
        id="identical-headline",
    ),
    pytest.param(
        ("physics-world", "How the Nancy Grace Roman Space Telescope will turn the sky into a dataset"),
        ("physics-world", "NASA launches Nancy Grace Roman Space Telescope to shed light on dark energy"),
        id="rewritten-headline",  # 5 shared words at overlap 0.62
    ),
    pytest.param(
        ("physics-world", "Quiz of the week: how far ahead can we predict the weather?"),
        ("physics-world", "How far ahead can we predict the weather?"),
        id="quiz-and-article",
    ),
]

# A recurring programme reuses one title for every episode. Three shared words at a perfect ratio,
# so only MIN_SHARED_WORDS = 4 keeps these apart; at 3 every episode becomes one story.
RECURRING_TITLES = [
    (("bbc-science", "BBC Inside Science"), ("bbc-science", "BBC Inside Science")),
    (("bbc-science", "Watch: Starship splashdown ends in fireball"),
     ("bbc-science", "Watch: From launch to fiery splashdown, SpaceX's Starship completes its flight")),
]

# Different outlets, different stories, sharing generic physics words at overlap 0.50 or below.
UNRELATED_ACROSS_OUTLETS = [
    (("aps-physics", "Unpacking Particle Showers with Machine Learning"),
     ("physics-world", "Improved QLEDs with Machine Learning")),
    (("nature-physics", "Fully developed active turbulence defined through a non-equilibrium phase transition"),
     ("aps-physics", "Phase Transition in Ant Colonies")),
    (("aps-physics", "A Climate for Physicists"),
     ("bbc-science", "Young minds develop ideas to tackle climate change")),
    (("nature-physics", "Topology from disorder"),
     ("physics-world", "Skyrmion topology makes long-distance optical communications more robust")),
]


def item(source: str, title: str, n: int) -> Item:
    return Item(
        id=f"url:https://{source}.test/{n}",
        title=title,
        url=f"https://{source}.test/{n}",
        published="2026-10-01T09:00:00Z",
        summary="",
        source=source,
        source_name=source,
        tier=2,
        kind="news",
    )


def group_sizes(*pairs) -> list[int]:
    items = [item(src, title, n) for n, (src, title) in enumerate(pairs)]
    return sorted((len(g.items) for g in group_items(items)), reverse=True)


@pytest.mark.parametrize("a,b", SAME_OUTLET_DUPLICATES)
def test_merges_one_outlet_reposting_the_same_story(a, b):
    assert group_sizes(a, b) == [2]


def test_merge_is_reported_as_a_headline_match_not_a_paper_match():
    a, b = SAME_OUTLET_DUPLICATES[0].values
    (group,) = group_items([item(src, title, n) for n, (src, title) in enumerate((a, b))])
    assert [e.reason for e in group.evidence] == ["similar_headline"]


@pytest.mark.parametrize("a,b", RECURRING_TITLES)
def test_keeps_episodes_of_a_recurring_title_apart(a, b):
    assert group_sizes(a, b) == [1, 1]


def test_six_episodes_sharing_one_title_stay_six_stories():
    episodes = [("bbc-science", "BBC Inside Science")] * 6
    assert group_sizes(*episodes) == [1, 1, 1, 1, 1, 1]


@pytest.mark.parametrize("a,b", UNRELATED_ACROSS_OUTLETS)
def test_leaves_unrelated_outlets_apart(a, b):
    assert group_sizes(a, b) == [1, 1]


def test_a_shared_identifier_merges_across_outlets_regardless_of_headline():
    a = item("quanta", "Mathematicians crack a 55-year-old problem", 1)
    b = item("nature-physics", "Topology from disorder", 2)
    a.identifiers = b.identifiers = ["arxiv:2204.09666"]
    (group,) = group_items([a, b])
    assert len(group.items) == 2
    assert [e.reason for e in group.evidence] == ["same_paper"]
