from dataclasses import dataclass

from app.services.search_client import SearchError, SearchResponse
from app.services.section_resource_recommendations import SectionResourceRecommendationService


@dataclass
class Item:
    title: str
    url: str
    snippet: str
    source: str = "duckduckgo"


class FakeClient:
    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        return SearchResponse(query=query, results=[
            Item("数组与链表课程", "https://ocw.mit.edu/course?utm_source=test", "数组、链表和时间复杂度。"),
            Item("数组与链表课程", "https://ocw.mit.edu/course", "重复标题和链接。"),
            Item("链表视频", "https://www.bilibili.com/video/BV1x", "链表操作演示。"),
            Item("无效", "javascript:alert(1)", "不能展示。"),
        ])


class UnavailableClient:
    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        raise SearchError("network unavailable")


def main() -> None:
    service = SectionResourceRecommendationService(client=FakeClient())
    result = service.recommend(section_id="s1", section_title="数组与链表", knowledge_points=["时间复杂度", "链表"], resource_types=["video"])
    assert result["status"] == "completed"
    assert len(result["query"]) == 3 and len(result["resources"]) == 2
    assert result["resources"][0]["url"].startswith("https://")
    assert all("example.com" not in item["url"] for item in result["resources"])
    assert {item["resource_type"] for item in result["resources"]} == {"course", "video"}
    assert all(item["reason"] and item["relevance_score"] <= 1 for item in result["resources"])

    unavailable = SectionResourceRecommendationService(client=UnavailableClient()).recommend(section_id="s1", section_title="数组", knowledge_points=[])
    assert unavailable["status"] == "search_unavailable" and not unavailable["resources"]
    print("section resource recommendations: PASS")


if __name__ == "__main__":
    main()
