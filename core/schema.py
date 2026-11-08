from dataclasses import dataclass, field, asdict

@dataclass
class Section:
    title: str
    paragraphs: list[str] = field(default_factory=list)
    children: list["Section"] = field(default_factory=list)

@dataclass
class Document:
    kind: str
    language: str
    title: str
    seed: int
    facts: dict
    sections: list[Section]
    placements: list[str]

    def to_dict(self):
        return asdict(self)
