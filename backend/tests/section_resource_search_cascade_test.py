from dataclasses import dataclass

from app.services.search_client import SearchResponse
from app.services.section_resource_recommendations import SearchCascade, SectionResourceRecommendationService


@dataclass
class Item:
    title: str
    url: str
    snippet: str
    source: str = "fake"


class CascadeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        self.calls.append(query)
        if len(self.calls) == 1:
            return SearchResponse(query=query, results=[], source="fake")
        items = [
            Item(
                title=f"recursion call stack tutorial {index}",
                url=f"https://docs{index}.example.edu/recursion/{index}",
                snippet="recursion call stack stack frame walkthrough tutorial",
            )
            for index in range(6)
        ]
        return SearchResponse(query=query, results=items, total_estimated=len(items), source="fake")


def main() -> None:
    SearchCascade.clear()
    client = CascadeClient()
    service = SectionResourceRecommendationService(client=client)
    service._use_cache = True  # Exercise the process cache without a network provider.
    events: list[dict] = []
    payload = dict(
        session_id="private-session",
        section_id="section-1",
        section_title="recursion call stack",
        resource_types=["article"],
        progress_callback=events.append,
    )
    first = service.recommend(**payload)
    assert first["status"] == "completed" and first["resources"]
    assert len(client.calls) == 2
    assert any(event["stage"] == "fallback_search" for event in events)
    assert events[-1]["stage"] == "completed"
    second = service.recommend(**payload)
    assert second["resources"] and len(client.calls) == 2
    assert not any("private-session" in str(event) for event in events)
    print("section resource cascade: PASS")


if __name__ == "__main__":
    main()
