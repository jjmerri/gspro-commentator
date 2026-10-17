from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from ..models import HoleChangeEvent, ShotEvent


class ShotSource(ABC):
    @abstractmethod
    def events(self) -> AsyncIterator[ShotEvent | HoleChangeEvent]:
        """Yield events until the source is exhausted or cancelled."""
