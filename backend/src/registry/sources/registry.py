from registry.sources.base import SourceConnector
from registry.sources.states.california import CaliforniaStubConnector
from registry.sources.states.florida import FloridaRegistryCsvConnector
from registry.sources.states.iowa import IowaRegistryApiConnector
from registry.sources.states.michigan import MichiganRegistryConnector
from registry.sources.states.minnesota import MinnesotaRegistryConnector
from registry.sources.states.nebraska import NebraskaRegistryConnector
from registry.sources.states.missouri import MissouriRegistryConnector
from registry.sources.states.north_dakota import NorthDakotaRegistryConnector
from registry.sources.states.north_carolina import NorthCarolinaRegistryConnector
from registry.sources.states.south_dakota import SouthDakotaRegistryConnector
from registry.sources.states.texas import TexasRegistryConnector
from registry.sources.states.wisconsin import WisconsinRegistryConnector

CONNECTORS: dict[str, type[SourceConnector]] = {
    "california": CaliforniaStubConnector,
    "iowa": IowaRegistryApiConnector,
    "michigan": MichiganRegistryConnector,
    "minnesota": MinnesotaRegistryConnector,
    "nebraska": NebraskaRegistryConnector,
    "missouri": MissouriRegistryConnector,
    "north-dakota": NorthDakotaRegistryConnector,
    "north-carolina": NorthCarolinaRegistryConnector,
    "south-dakota": SouthDakotaRegistryConnector,
    "texas": TexasRegistryConnector,
    "wisconsin": WisconsinRegistryConnector,
}

if FloridaRegistryCsvConnector.is_configured():
    CONNECTORS["florida"] = FloridaRegistryCsvConnector


def list_connectors() -> list[SourceConnector]:
    return [connector_cls() for connector_cls in CONNECTORS.values()]


def get_connector(source: str) -> SourceConnector:
    try:
        return CONNECTORS[source]()
    except KeyError as exc:
        available = ", ".join(sorted(CONNECTORS))
        raise ValueError(f"Unknown source '{source}'. Available sources: {available}") from exc
