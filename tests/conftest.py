import pytest

from gatoway import router


@pytest.fixture(autouse=True)
def _default_strict_routing_off(monkeypatch):
    """Pin the strict-routing gate OFF for every test.

    ``GATOWAY_STRICT_ROUTING`` is read at import time, and ``providers`` calls
    ``load_dotenv()`` on import, so an ambient value (a developer's ``.env``,
    CI, a shell export) would otherwise flip routing mid-suite and break the
    default-behavior tests. Strict-path tests opt in with their own
    ``monkeypatch.setattr(router, "STRICT_ROUTING", True)``.
    """
    monkeypatch.setattr(router, "STRICT_ROUTING", False)
