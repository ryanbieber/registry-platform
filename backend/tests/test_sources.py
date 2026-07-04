from registry.sources.registry import get_connector, list_connectors


def test_list_connectors_contains_california() -> None:
    names = [connector.name for connector in list_connectors()]
    assert "california" in names


def test_get_connector() -> None:
    connector = get_connector("california")
    assert connector.state == "CA"
