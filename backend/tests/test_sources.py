from registry.sources.registry import get_connector, list_connectors


def test_list_connectors_contains_california() -> None:
    names = [connector.name for connector in list_connectors()]
    assert "california" in names
    assert "iowa" in names
    assert "michigan" in names
    assert "minnesota" in names
    assert "nebraska" in names
    assert "missouri" in names
    assert "north-dakota" in names
    assert "north-carolina" in names
    assert "south-dakota" in names
    assert "texas" in names
    assert "wisconsin" in names


def test_get_connector() -> None:
    connector = get_connector("california")
    assert connector.state == "CA"


def test_get_iowa_connector() -> None:
    connector = get_connector("iowa")
    assert connector.state == "IA"


def test_get_michigan_connector() -> None:
    connector = get_connector("michigan")
    assert connector.state == "MI"


def test_get_minnesota_connector() -> None:
    connector = get_connector("minnesota")
    assert connector.state == "MN"


def test_get_nebraska_connector() -> None:
    connector = get_connector("nebraska")
    assert connector.state == "NE"


def test_get_missouri_connector() -> None:
    connector = get_connector("missouri")
    assert connector.state == "MO"


def test_get_north_dakota_connector() -> None:
    connector = get_connector("north-dakota")
    assert connector.state == "ND"


def test_get_north_carolina_connector() -> None:
    connector = get_connector("north-carolina")
    assert connector.state == "NC"


def test_get_south_dakota_connector() -> None:
    connector = get_connector("south-dakota")
    assert connector.state == "SD"


def test_get_texas_connector() -> None:
    connector = get_connector("texas")
    assert connector.state == "TX"


def test_get_wisconsin_connector() -> None:
    connector = get_connector("wisconsin")
    assert connector.state == "WI"
