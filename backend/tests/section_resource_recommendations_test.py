from collections import Counter
from dataclasses import dataclass

from app.services.search_client import SearchError, SearchResponse
from app.services.section_resource_recommendations import (
    SectionResourceRecommendationService,
    classify_platform,
    normalize_search_context,
)


@dataclass
class Item:
    title: str
    url: str
    snippet: str
    source: str = "duckduckgo"


class TypedClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        self.queries.append(query)
        if "bilibili.com/video" in query:
            items = [Item("\u9012\u5f52\u8c03\u7528\u6808\u89c6\u9891", "https://www.bilibili.com/video/BV1recursion", "\u9636\u4e58\u9012\u5f52\u5c55\u793a\u6808\u5e27\u53d8\u5316")]
        elif "youtube.com/watch" in query:
            items = [Item("Recursion call stack tutorial", "https://www.youtube.com/watch?v=callstack", "stack frame and local variables walkthrough")]
        elif "icourse163.org" in query:
            items = [Item("\u6570\u636e\u7ed3\u6784\u8bfe\u7a0b\uff1a\u9012\u5f52", "https://www.icourse163.org/learn/DS-100", "\u516c\u5f00\u8bfe\u7a0b\u7ae0\u8282\u5305\u542b\u9012\u5f52\u548c\u6808")]
        elif "xuetangx.com" in query:
            items = [Item("\u9012\u5f52\u4e0e\u8c03\u7528\u6808\u8bfe\u7a0b", "https://www.xuetangx.com/learn/ds/recursion", "\u6570\u636e\u7ed3\u6784\u5b66\u4e60\u6a21\u5757")]
        elif "filetype:pdf" in query and "\u8bfe\u4ef6" in query:
            items = [Item("\u9012\u5f52\u8c03\u7528\u6808\u8bfe\u4ef6", "https://cs.example.edu/slides/recursion-stack.pdf", "\u9ad8\u6821\u8bfe\u4ef6\uff1a\u6808\u5e27\u548c\u8fd4\u56de\u5730\u5740")]
        elif "filetype:pdf" in query:
            items = [Item("\u9012\u5f52\u8c03\u7528\u6808\u8bb2\u4e49", "https://cs.example.edu/notes/recursion-stack.pdf", "\u5927\u5b66\u8bb2\u4e49\uff1a\u9012\u5f52\u3001\u6808\u5e27\u548c\u5c40\u90e8\u53d8\u91cf")]
        elif "arxiv.org" in query:
            items = [Item("Recursion Runtime Stack Study", "https://arxiv.org/abs/2401.12345", "recursion call stack and stack frame analysis")]
        elif "semanticscholar.org" in query:
            items = [Item("Call Stack Research", "https://www.semanticscholar.org/paper/call-stack", "recursion runtime stack research")]
        elif "\u9636\u4e58" in query:
            items = [Item("\u9012\u5f52\u8c03\u7528\u6808\u793a\u4f8b", "https://tutorial.example.org/factorial-call-stack", "\u9636\u4e58\u548c\u6590\u6ce2\u90a3\u5951\u9012\u5f52\u7684\u8c03\u7528\u6808\u793a\u4f8b")]
        else:
            items = [
                Item("\u9012\u5f52\u8c03\u7528\u6808\u6559\u7a0b", "https://cs.example.edu/tutorials/recursion-call-stack", "\u6570\u636e\u7ed3\u6784\u4e2d\u7684\u9012\u5f52\u3001\u8c03\u7528\u6808\u548c\u6808\u5e27"),
                Item("\u666e\u901a\u535a\u5ba2", "https://blog.example.com/recursion", "\u9012\u5f52\u8c03\u7528\u6808"),
                Item("\u9012\u5f52 \u8c03\u7528\u6808 \u6808\u5e27 \u9636\u4e58 \u6559\u7a0b", "https://article-one.test/recursion", "\u9012\u5f52 \u8c03\u7528\u6808 \u6808\u5e27 \u5c40\u90e8\u53d8\u91cf \u8fd4\u56de\u5730\u5740"),
                Item("\u9012\u5f52 \u8c03\u7528\u6808 \u6808\u5e27 \u6590\u6ce2\u90a3\u5951 \u6559\u7a0b", "https://article-two.test/recursion", "\u9012\u5f52 \u8c03\u7528\u6808 \u6808\u5e27 \u5c40\u90e8\u53d8\u91cf \u8fd4\u56de\u5730\u5740"),
                Item("\u9012\u5f52 \u8c03\u7528\u6808 \u6808\u5e27 \u793a\u4f8b", "https://article-three.test/recursion", "\u9012\u5f52 \u8c03\u7528\u6808 \u6808\u5e27 \u5c40\u90e8\u53d8\u91cf \u8fd4\u56de\u5730\u5740"),
            ]
        return SearchResponse(query=query, results=items, total_estimated=len(items), source="fake")


class ExpandedPaperClient(TypedClient):
    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        self.queries.append(query)
        if "tail recursion" in query:
            item = Item("Tail Recursion Optimization", "https://arxiv.org/abs/2402.54321", "tail recursion runtime stack optimization")
            return SearchResponse(query=query, results=[item], total_estimated=1, source="fake")
        return SearchResponse(query=query, results=[], total_estimated=0, source="fake")


class UnavailableClient:
    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        raise SearchError("network unavailable")


def recommend(service: SectionResourceRecommendationService, resource_type: str) -> dict:
    return service.recommend(
        session_id="test", section_id="s1",
        section_title="\u7528\u7eb8\u7b14\u624b\u52a8\u6a21\u62df\u4e00\u4e2a\u7b80\u5355\u9012\u5f52\u51fd\u6570\uff08\u5982\u9636\u4e58\u3001\u6590\u6ce2\u90a3\u5951\uff09\u7684\u8c03\u7528\u6808\u53d8\u5316\uff0c\u753b\u51fa\u6bcf\u4e00\u5c42\u6808\u5e27\u7684\u5c40\u90e8\u53d8\u91cf\u548c\u8fd4\u56de\u5730\u5740",
        resource_types=[resource_type], profile={"subject_context": {"subject_name": "\u6570\u636e\u7ed3\u6784", "content_preferences": ["example_first"]}},
        collect_diagnostics=True,
    )


def main() -> None:
    context = normalize_search_context(
        course_name="\u6570\u636e\u7ed3\u6784",
        section_title="\u7528\u7eb8\u7b14\u624b\u52a8\u6a21\u62df\u4e00\u4e2a\u7b80\u5355\u9012\u5f52\u51fd\u6570\uff08\u5982\u9636\u4e58\u3001\u6590\u6ce2\u90a3\u5951\uff09\u7684\u8c03\u7528\u6808\u53d8\u5316\uff0c\u753b\u51fa\u6bcf\u4e00\u5c42\u6808\u5e27\u7684\u5c40\u90e8\u53d8\u91cf\u548c\u8fd4\u56de\u5730\u5740",
    )
    assert context["primary_topic"] == "\u9012\u5f52\u8c03\u7528\u6808"
    assert {"\u9012\u5f52", "\u8c03\u7528\u6808", "\u6808\u5e27", "\u9636\u4e58", "\u6590\u6ce2\u90a3\u5951"}.issubset(context["keywords"])
    assert "\u7528\u7eb8\u7b14" not in context["keywords"] and "\u753b\u51fa" not in context["keywords"]

    assert classify_platform("https://www.bilibili.com/video/BV1x") == "bilibili"
    assert classify_platform("https://www.youtube.com/watch?v=abc") == "youtube"
    assert classify_platform("https://www.youtube.com/results?search_query=array") is None
    assert classify_platform("https://www.youku.com/v_show/id_X.html") == "youku"
    assert classify_platform("https://www.iqiyi.com/v_123.html") == "iqiyi"
    assert classify_platform("https://www.douyin.com/video/123456") == "douyin"

    service = SectionResourceRecommendationService(client=TypedClient())
    for resource_type in ("article", "video", "course", "document", "paper"):
        result = recommend(service, resource_type)
        assert result["status"] == "completed" and result["resources"]
        assert all(item["resource_type"] == resource_type for item in result["resources"])
        assert all("example.com" not in item["url"] for item in result["resources"])
        assert result["diagnostics"]["raw_count"] >= result["diagnostics"]["final_count"]
        assert result["diagnostics"]["url_valid_count"] >= result["diagnostics"]["relevance_candidate_count"]
    assert all("\u7528\u7eb8\u7b14" not in query and "\u624b\u52a8\u6a21\u62df" not in query for query in service._client.queries)

    mixed = service.recommend(session_id="test", section_id="s1", section_title="\u9012\u5f52\u8c03\u7528\u6808", resource_types=["article", "video", "course", "document", "paper"], profile={"subject_context": {"subject_name": "\u6570\u636e\u7ed3\u6784"}})
    assert {item["resource_type"] for item in mixed["resources"]} >= {"article", "video", "course", "document", "paper"}
    assert max(Counter(item["source"] for item in mixed["resources"]).values()) <= 2

    expanded = recommend(SectionResourceRecommendationService(client=ExpandedPaperClient()), "paper")
    assert expanded["resources"] and expanded["resources"][0]["match_level"] == "expanded_research"

    unavailable = SectionResourceRecommendationService(client=UnavailableClient()).recommend(session_id="test", section_id="s1", section_title="\u9012\u5f52", resource_types=["article"])
    assert unavailable["status"] == "search_unavailable" and not unavailable["resources"]
    personalized_client = TypedClient()
    personalized = SectionResourceRecommendationService(client=personalized_client).recommend(
        session_id="private_session", section_id="s2", section_title="递归调用栈", knowledge_points=["递归", "调用栈"],
        weak_points=["递归", "链表"], resource_types=["article"],
        profile={"subject_context": {"subject_name": "数据结构", "prior_experience": ["零基础"], "content_preferences": ["example_first"], "resource_preferences": ["视频"], "learning_goal": "张三的完整私人学习目标"}, "knowledge_mastery": [{"label": "递归", "status": "weak"}]},
    )
    assert any("示例" in query and "入门" in query for query in personalized_client.queries)
    assert all("张三" not in query and "私人学习目标" not in query and "private_session" not in query for query in personalized_client.queries)
    assert all("链表" not in query for query in personalized_client.queries)
    assert "先看例题偏好" in personalized["resources"][0]["reason"]
    print("section resource recommendations: PASS")


if __name__ == "__main__":
    main()
