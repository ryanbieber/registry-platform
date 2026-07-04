from registry.sources.base import SourceConnector
from registry.sources.states.california import CaliforniaStubConnector

CONNECTORS: dict[str, type[SourceConnector]] = {
    "california": CaliforniaStubConnector,
}


def list_connectors() -> list[SourceConnector]:
    return [connector_cls() for connector_cls in CONNECTORS.values()]


def get_connector(source: str) -> SourceConnector:
    try:
        return CONNECTORS[source]()
    except KeyError as exc:
        available = ", ".join(sorted(CONNECTORS))
        raise ValueError(f"Unknown source '{source}'. Available sources: {available}") from exc
