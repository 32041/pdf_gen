import random
from collections import Counter

def allocate(weights, count, rng):
    """Largest remainder quotas; shuffle assignment without changing counts."""
    if not weights or any(v < 0 for v in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("Weights must be nonnegative with positive total")
    total = sum(weights.values())
    raw = {k: v * count / total for k, v in weights.items()}
    counts = {k: int(v) for k, v in raw.items()}
    order = sorted(raw, key=lambda k: raw[k] - counts[k], reverse=True)
    for k in order[:count - sum(counts.values())]:
        counts[k] += 1
    result = [k for k, n in counts.items() for _ in range(n)]
    rng.shuffle(result)
    return result

def validate_sections(sections):
    for section in sections:
        if len(section.children) == 1:
            raise ValueError(f"Singleton heading under {section.title}")
        validate_sections(section.children)

def validate_document(doc):
    validate_sections(doc.sections)
    f = doc.facts
    assert all(abs(r-c-p) < 1e-8 for r,c,p in zip(f['revenue'],f['cost'],f['profit']))
