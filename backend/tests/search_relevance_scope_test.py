"""Keep task-scoped resource search relevant without provider calls."""
from dataclasses import dataclass
from app.services.search_client import SearchResponse
from app.services.section_resource_recommendations import SectionResourceRecommendationService, normalize_search_context

@dataclass
class Item:
    title: str
    url: str
    snippet: str

class Client:
    def search(self, query, max_results=5):
        return SearchResponse(query=query, source="test", results=[
            Item("Learn Greek in 30 Minutes", "https://www.youtube.com/watch?v=greek", "Greek language lesson"),
            Item("Big O Time Complexity", "https://www.youtube.com/watch?v=bigo", "data structures time complexity tutorial"),
        ])

def main():
    service = SectionResourceRecommendationService(client=Client())
    result = service.recommend(session_id="learner", section_id="task-a", section_title="时间复杂度与线性表", course_name="数据结构", resource_types=["video"])
    assert [item["title"] for item in result["resources"]] == ["Big O Time Complexity"]
    context = normalize_search_context(course_name="数据结构", section_title="时间复杂度")
    assert service._cache_key(context, ["video"], "zh-CN", "a|task-a") != service._cache_key(context, ["video"], "zh-CN", "a|task-b")
    print("search relevance scope: PASS")

if __name__ == "__main__":
    main()
