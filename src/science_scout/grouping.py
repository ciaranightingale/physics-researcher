"""Grouping items that are about the same story. Deterministic: same items in, same groups out.

Two items join the same group when:
  1. they share a paper identifier (a DOI or arXiv ID)            -> reason "same_paper"  (strong)
  2. their headlines share enough content words                   -> reason "similar_headline" (weaker; check these)
Groups are transitive: if A~B and B~C, all three end up together.
"""

import hashlib
from collections import defaultdict

from .models import Item, MatchEvidence
from .normalise import headline_overlap, headline_tokens

MIN_OVERLAP = 0.6
MIN_SHARED_WORDS = 4
_KIND_PRIORITY = {"news": 0, "press-office": 1, "journal": 2, "preprint": 3}


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[max(ra, rb)] = min(ra, rb)
        return True


class RawGroup:
    def __init__(self, items: list[Item], evidence: list[MatchEvidence]):
        self.items = sorted(items, key=lambda i: (i.tier if i.tier else 9, i.published, i.id))
        self.evidence = evidence
        self.identifiers = sorted({ident for i in items for ident in i.identifiers})
        anchor = self.identifiers[0] if self.identifiers else min(i.id for i in items)
        self.group_id = "g_" + hashlib.sha1(anchor.encode()).hexdigest()[:10]
        # Readable headline: prefer journalism over press releases over paper titles; earliest wins ties.
        self.headline = min(items, key=lambda i: (_KIND_PRIORITY[i.kind], i.published, i.id)).title
        self.latest_published = max(i.published for i in items)

    @property
    def keys(self) -> list[str]:
        """Everything that identifies this story: each source's link key plus the paper identifiers."""
        return sorted({i.id for i in self.items} | set(self.identifiers))


def group_items(items: list[Item]) -> list[RawGroup]:
    items = sorted(items, key=lambda i: i.id)  # fixed order in, fixed groups out
    uf = _UnionFind(len(items))
    evidence: list[tuple[int, MatchEvidence]] = []

    by_ident: dict[str, list[int]] = defaultdict(list)
    for idx, it in enumerate(items):
        for ident in it.identifiers:
            by_ident[ident].append(idx)
    for ident in sorted(by_ident):
        members = by_ident[ident]
        if len(members) > 1:
            for m in members[1:]:
                uf.union(members[0], m)
            evidence.append((members[0], MatchEvidence(reason="same_paper", detail=f"all link to {ident}", items=[items[m].id for m in members])))

    tokens = [headline_tokens(it.title) for it in items]
    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            score, shared = headline_overlap(tokens[a], tokens[b])
            if score >= MIN_OVERLAP and len(shared) >= MIN_SHARED_WORDS and uf.find(a) != uf.find(b):
                uf.union(a, b)
                detail = f"headlines share {len(shared)} words ({', '.join(sorted(shared))}), overlap {score:.2f}"
                evidence.append((a, MatchEvidence(reason="similar_headline", detail=detail, items=[items[a].id, items[b].id])))

    members: dict[int, list[int]] = defaultdict(list)
    for idx in range(len(items)):
        members[uf.find(idx)].append(idx)
    ev_by_root: dict[int, list[MatchEvidence]] = defaultdict(list)
    for idx, ev in evidence:
        ev_by_root[uf.find(idx)].append(ev)

    groups = [RawGroup([items[i] for i in idxs], ev_by_root[root]) for root, idxs in members.items()]
    return sorted(groups, key=lambda g: (g.latest_published, g.group_id), reverse=True)
