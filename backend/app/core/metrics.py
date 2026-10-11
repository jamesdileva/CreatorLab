"""Rank-correlation metrics — shared by concept scoring now and reality-gap later
(architecture §12: Spearman, Kendall, top-k, directional accuracy)."""
from statistics import mean


def _ranks(values: list[float]) -> list[float]:
    """Average ranks (ties share the mean of their positions)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("spearman needs equal-length sequences of >= 2 items")
    rx, ry = _ranks(x), _ranks(y)
    mx, my = mean(rx), mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (
        sum((a - mx) ** 2 for a in rx) ** 0.5 * sum((b - my) ** 2 for b in ry) ** 0.5
    )
    if den == 0:
        return 0.0
    return max(-1.0, min(1.0, num / den))


def kendall_tau(x: list[float], y: list[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("kendall needs equal-length sequences of >= 2 items")
    concordant = discordant = 0
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            sx = (x[i] > x[j]) - (x[i] < x[j])
            sy = (y[i] > y[j]) - (y[i] < y[j])
            if sx * sy > 0:
                concordant += 1
            elif sx * sy < 0:
                discordant += 1
    total = concordant + discordant
    if total == 0:
        return 0.0
    return (concordant - discordant) / total


def top_k_agreement(rank_a: list, rank_b: list, k: int | None = None) -> float:
    """Share of the shared k top items (k = min length by default)."""
    if not rank_a or not rank_b:
        return 0.0
    k = min(k or min(len(rank_a), len(rank_b)), len(rank_a), len(rank_b))
    return len(set(rank_a[:k]) & set(rank_b[:k])) / k


def directional_accuracy(rank_a: list, rank_b: list) -> float:
    """Fraction of item pairs whose relative order agrees in both rankings.

    Both arguments are item sequences ordered best-first; agreement is judged
    on the same item pairs seen through each ranking.
    """
    pos_b = {item: i for i, item in enumerate(rank_b)}
    pairs = [
        (rank_a[i], rank_a[j])
        for i in range(len(rank_a))
        for j in range(i + 1, len(rank_a))
        if rank_a[i] in pos_b and rank_a[j] in pos_b
    ]
    if not pairs:
        return 0.0
    agree = sum(1 for x, y in pairs if pos_b[x] < pos_b[y])
    return agree / len(pairs)
