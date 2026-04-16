from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass
class ClassificationResult:
    status: str
    spans: list[str]


ProgressCallback = Callable[[int, int, int, dict[str, int]], None]


class Classifier(Protocol):
    def classify(self, text: str) -> ClassificationResult:
        ...

