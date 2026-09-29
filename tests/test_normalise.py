from science_scout.normalise import canonical_url, extract_identifiers, headline_overlap, headline_tokens, item_key


def test_canonical_url_strips_tracking_www_and_trailing_slash():
    assert canonical_url("http://WWW.Example.com/a/b/?utm_source=rss&z=1&a=2#frag") == "https://example.com/a/b?a=2&z=1"


def test_arxiv_links_all_map_to_one_key():
    keys = {item_key(u) for u in ["https://arxiv.org/abs/2609.04567", "http://arxiv.org/pdf/2609.04567v3", "https://arxiv.org/abs/2609.04567v1"]}
    assert keys == {"arxiv:2609.04567"}


def test_identifier_extraction_across_publishers():
    text = """
      https://doi.org/10.1038/s41567-026-00001-x.
      https://www.nature.com/articles/s41586-026-01234-5
      https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.136.123401
      https://www.science.org/doi/full/10.1126/science.adq1234
      https://doi.org/10.48550/arXiv.2609.00042
      as reported in arXiv:2609.01234v2 (see also https://arxiv.org/pdf/2609.01234)
    """
    assert extract_identifiers(text) == [
        "doi:10.1038/s41567-026-00001-x",
        "doi:10.1038/s41586-026-01234-5",
        "doi:10.1103/physrevlett.136.123401",
        "doi:10.1126/science.adq1234",
        "arxiv:2609.00042",
        "arxiv:2609.01234",
    ]


def test_headline_similarity():
    a = headline_tokens("Record-breaking black hole merger spotted by gravitational wave detectors")
    b = headline_tokens("Heaviest black hole merger yet detected by gravitational wave observatories")
    score, shared = headline_overlap(a, b)
    assert shared == {"black", "hole", "merger", "gravitational", "wave"}
    assert score >= 0.6
    unrelated, _ = headline_overlap(a, headline_tokens("Twisted graphene reveals a new quantum phase"))
    assert unrelated == 0


def test_days_since():
    from datetime import datetime, timezone

    from science_scout.normalise import days_since

    now = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
    assert days_since("2026-09-10T08:00:00Z", now) == 0
    assert days_since("2026-09-02T12:00:00Z", now) == 8
    assert days_since("2026-09-11T12:00:00Z", now) == 0  # future-dated items don't go negative
