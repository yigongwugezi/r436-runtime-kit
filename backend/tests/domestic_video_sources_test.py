"""Domestic-first video selection regression."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.section_resource_recommendations import SectionResourceRecommendationService, validate_resource_url


def main():
    service = SectionResourceRecommendationService(client=object())
    both = [
        {"resource_type": "video", "platform": "youtube", "url": "https://youtube.com/watch?v=x"},
        {"resource_type": "video", "platform": "bilibili", "url": "https://bilibili.com/video/BV1x"},
    ]
    assert [item["platform"] for item in service._prefer_domestic_videos(both)] == ["bilibili"]
    overseas = service._prefer_domestic_videos([{ "resource_type": "video", "platform": "youtube", "url": "https://youtube.com/watch?v=x" }])
    assert overseas[0]["access_region"] == "overseas" and overseas[0]["access_note"] == "部分地区可能无法访问"
    assert "site:bilibili.com/video" in service._query_layers({"course_name": "数据结构", "primary_topic": "时间复杂度", "keywords": [], "english_keywords": [], "preferences": [], "level": "general"}, "video", "zh-CN")[0][0]
    assert not validate_resource_url("https://www.youtube.com/results?search_query=greek", "video")
    print("domestic video sources: PASS")


if __name__ == "__main__": main()
