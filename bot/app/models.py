from dataclasses import dataclass


@dataclass(frozen=True)
class WatchRequestResult:
    mode: str
    variant_id: int
    title_id: int
    episode_id: int | None
