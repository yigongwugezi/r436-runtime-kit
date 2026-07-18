import os
os.environ["EDUAGENT_SKIP_ENV_FILE"] = "1"
os.environ["LLM_PROVIDER"] = "mock"

from unittest.mock import patch
from app.routers.product import _general_resource_payload, normalize_general_resource_request


def main():
    request = normalize_general_resource_request({"sessionId": "s", "subjectId": "x", "topic": "derivative", "resourceType": "mindmap"})
    with patch("app.services.deeptutor_client.generate_mindmap", return_value=""):
        resource = _general_resource_payload(request)
    assert resource["mermaid_def"].startswith("mindmap")
    assert resource["content"]
    print("resource provider fallback: PASS")


if __name__ == "__main__":
    main()
