import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def assert_true(value, label: str) -> None:
    if not value:
        raise AssertionError(label)


def main() -> None:
    from app.main import app  # noqa: WPS433

    paths = {route.path for route in app.routes}
    assert_true("/api/health" in paths, "health route should exist")
    assert_true("/api/courses" in paths, "courses route should exist")
    assert_true("/api/agents/run" in paths, "agents route should exist")
    assert_true("/api/chat/send" in paths, "chat route should exist")
    print("PASS import_app_test")


if __name__ == "__main__":
    main()
