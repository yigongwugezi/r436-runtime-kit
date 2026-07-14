from dataclasses import dataclass
from threading import Event

from app.services.profile_v2 import build_profile_v2, personalization_context, update_fact_control
from app.services.search_client import SearchResponse
from app.services.section_resource_recommendations import SearchCascade, SectionResourceRecommendationService


@dataclass
class Item:
    title: str
    url: str
    snippet: str


class FastClient:
    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        return SearchResponse(query, [Item("递归调用栈教程", "https://docs.example.edu/recursion", "递归调用栈和栈帧示例")])


def main() -> None:
    service = SectionResourceRecommendationService(client=FastClient())
    cancelled = service.recommend(session_id="s", section_id="x", section_title="递归调用栈", resource_types=["article"], cancel_event=Event())
    assert cancelled["status"] == "completed"
    event = Event(); event.set()
    cancelled = service.recommend(session_id="s", section_id="x", section_title="递归调用栈", resource_types=["article"], cancel_event=event)
    assert cancelled["status"] == "cancelled"

    profile = build_profile_v2(facts={"target_course": "数据结构", "preference": "图解"}, course={"course_name": "数据结构", "course_id": "ds"})
    assert profile["fact_records"]["content_preferences"]["fact_type"] == "explicit"
    update_fact_control(profile, "content_preferences", "disable")
    assert "content_preferences" not in personalization_context(profile)
    update_fact_control(profile, "content_preferences", "enable")
    assert "content_preferences" in personalization_context(profile)
    print("p5 hardening: PASS")


if __name__ == "__main__":
    SearchCascade.clear()
    main()
