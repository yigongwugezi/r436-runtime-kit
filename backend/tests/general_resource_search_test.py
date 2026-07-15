"""Local-only checks for the generic online resource-search boundary."""

from dataclasses import dataclass

from app.routers.product import normalize_resource_search_request
from app.services.search_client import SearchError, SearchResponse
from app.services.section_resource_recommendations import SearchCascade, SectionResourceRecommendationService, normalize_search_topic
from app.services.workflow_tasks import WorkflowTaskManager


@dataclass
class Item:
    title: str
    url: str
    snippet: str
    source: str = "fixture"


class GenericSearchClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        self.calls.append(query)
        if "视频" in query or "video" in query.lower():
            item = Item("递归调用栈视频", "https://www.bilibili.com/video/BV1fixture", "递归调用栈和栈帧")
        elif "课程" in query or "mooc" in query.lower():
            item = Item("递归调用栈课程", "https://www.icourse163.org/learn/DS-100", "递归调用栈课程")
        elif "课件" in query or "讲义" in query or "lecture notes" in query.lower():
            item = Item("递归调用栈讲义", "https://cs.fixture.edu/notes/recursion-call-stack.pdf", "递归调用栈讲义")
        elif "paper" in query.lower() or "research" in query.lower():
            item = Item("Recursion Call Stack Study", "https://arxiv.org/abs/2401.12345", "recursion call stack stack frame")
        else:
            item = Item("递归调用栈文章", "https://learn.fixture.edu/recursion-call-stack", "递归调用栈和栈帧")
        return SearchResponse(query=query, results=[item], total_estimated=1, source="fixture")


class UnavailableClient:
    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        raise SearchError("fixture unavailable")


def main() -> None:
    expected = {
        "递归调用栈": "递归调用栈",
        "数组与链表": "数组与链表",
        "二叉树层序遍历": "二叉树层序遍历",
        "C++ 模板": "C++ 模板",
        "操作系统进程与线程": "操作系统进程与线程",
        "数据结构、": "数据结构",
    }
    for raw, canonical in expected.items():
        assert normalize_search_topic(raw) == canonical
        request = normalize_resource_search_request({"sessionId": "s", "query": raw})
        assert request["query"] == canonical and request["canonicalQuery"] == canonical

    manager = WorkflowTaskManager()
    first = normalize_resource_search_request({"sessionId": "s", "query": "递归调用栈、", "operation": "online_resource_search"})
    second = normalize_resource_search_request({"sessionId": "s", "query": "递归调用栈", "operation": "online_resource_search"})
    assert manager.canonical_task_key("resource_search", "learner", "s", "", first) == manager.canonical_task_key("resource_search", "learner", "s", "", second)

    SearchCascade.clear()
    SectionResourceRecommendationService._auto_ingest = lambda self, resources: None
    client = GenericSearchClient()
    service = SectionResourceRecommendationService(client=client)
    service._use_cache = True
    result = service.recommend(
        session_id="s", section_id="", section_title="递归调用栈",
        resource_types=["article", "video", "course", "document", "paper"],
    )
    assert result["canonical_query"] == "递归调用栈"
    assert result["context"]["topic"] == "递归调用栈"
    assert {item["resource_type"] for item in result["resources"]} == {"article", "video", "course", "document", "paper"}
    assert all(item["quality_status"] == "passed" for item in result["resources"])
    assert all("递归调用栈" in query or "recursion call stack" in query.lower() for query in client.calls)
    call_count = len(client.calls)
    cached = service.recommend(session_id="s", section_id="", section_title="递归调用栈", resource_types=["article", "video", "course", "document", "paper"])
    assert cached["resources"] and len(client.calls) == call_count

    unavailable = SectionResourceRecommendationService(client=UnavailableClient()).recommend(
        session_id="s", section_id="", section_title="递归调用栈", resource_types=["article"],
    )
    assert unavailable["status"] == "search_unavailable" and not unavailable["resources"]
    print("general resource search: PASS")


if __name__ == "__main__":
    main()
