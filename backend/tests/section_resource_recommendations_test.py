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
            Item("数组教程", "https://www.youtube.com/watch?v=abc", "数组和链表 walkthrough。"),
            Item("链表短视频", "https://www.youtube.com/shorts/xyz", "同平台结果，受数量限制。"),
            Item("复杂度课程视频", "https://vimeo.com/123456", "时间复杂度课程讲解。"),
            Item("无关视频", "https://vimeo.com/987654", "不含当前知识点。"),
            Item("YouTube 搜索页", "https://www.youtube.com/results?search_query=array", "不是具体视频。"),
            Item("B站首页", "https://www.bilibili.com/", "不是具体视频。"),
            Item("无效", "javascript:alert(1)", "不能展示。"),
        ])


class UnavailableClient:
    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        raise SearchError("network unavailable")


def main() -> None:
    service = SectionResourceRecommendationService(client=FakeClient())
    assert service._video_platform("https://www.bilibili.com/video/BV1x") == "bilibili"
    assert service._video_platform("https://www.youtube.com/watch?v=abc") == "youtube"
    assert service._video_platform("https://www.youtube.com/shorts/abc") == "youtube"
    assert service._video_platform("https://youtu.be/abc") == "youtube"
    assert service._video_platform("https://vimeo.com/123456") == "vimeo"
    assert service._video_platform("https://www.bilibili.com/") is None
    assert service._video_platform("https://www.youtube.com/results?search_query=array") is None
    result = service.recommend(session_id="test", section_id="s1", section_title="数组与链表", knowledge_points=["时间复杂度"], weak_points=[{"topic": "链表"}], resource_types=["video"], profile={"subject_context": {"content_preferences": ["example_first"]}})
    assert result["status"] == "completed"
    assert len(result["query"]) == 3 and result["resources"]
    assert any("链表" in query for query in result["query"])
    assert any("入门" in query and "示例" in query for query in result["query"])
    assert result["resources"][0]["url"].startswith("https://")
    assert all("example.com" not in item["url"] for item in result["resources"])
    assert all(item["resource_type"] == "video" for item in result["resources"])
    assert {item["platform"] for item in result["resources"]} >= {"bilibili", "youtube", "vimeo"}
    assert all("/results" not in item["url"] and item["url"] != "https://www.bilibili.com" for item in result["resources"])
    assert all(item["title"] != "无关视频" for item in result["resources"])
    assert all(item["reason"] and item["relevance_score"] <= 1 for item in result["resources"])

    mixed = service.recommend(session_id="test", section_id="s1", section_title="数组与链表", knowledge_points=[], resource_types=["video", "course"])
    assert {item["resource_type"] for item in mixed["resources"]} <= {"video", "course"}
    assert any(item["resource_type"] == "course" for item in mixed["resources"])

    unavailable = SectionResourceRecommendationService(client=UnavailableClient()).recommend(session_id="test", section_id="s1", section_title="数组", knowledge_points=[])
    assert unavailable["status"] == "search_unavailable" and not unavailable["resources"]
    print("section resource recommendations: PASS")


if __name__ == "__main__":
    main()
