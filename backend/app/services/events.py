from app.models import Signal, SignalKind
from app.repository import PathEventRecord


def confirmed_path_signals(
    events: list[PathEventRecord],
    symbol: str,
) -> list[Signal]:
    labels = {
        "upward_excursion": "Unusual upward excursion",
        "downward_excursion": "Unusual downward excursion",
        "peak_to_trough": "Spike reversed before the feed stopped",
        "trough_to_peak": "Drop recovered before the feed stopped",
    }
    return [
        Signal(
            kind=SignalKind.PATH_EVENT,
            label=labels.get(event.event_type, "Previously confirmed path event"),
            occurred_at=event.occurred_at,
            percentile=event.percentile,
            observation_count=int(event.evidence.get("observation_count", 0)) or None,
            direction=event.event_type,
            evidence={**event.evidence, "magnitude_percent": round(event.magnitude * 100, 2)},
        )
        for event in events
        if event.symbol == symbol
    ]
