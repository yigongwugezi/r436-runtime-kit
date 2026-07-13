from unittest.mock import patch

from app.services.search_client import DuckDuckGoSearchClient, SearchError


class AutoSuccess:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def text(self, query, **kwargs):
        self.calls.append((self.kwargs, query, kwargs))
        return [{"title": "时间复杂度教程", "href": "https://example.edu/complexity", "body": "真实字段转换"}]


class AutoFailsThenBing:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def text(self, query, **kwargs):
        self.calls.append((self.kwargs, query, kwargs))
        if kwargs["backend"] == "auto":
            raise RuntimeError("202 Ratelimit")
        return [{"title": "数组课程", "href": "https://example.edu/arrays", "body": "数组与链表"}]


class AlwaysFails:
    def __init__(self, **kwargs):
        pass

    def text(self, query, **kwargs):
        raise RuntimeError("provider unavailable")


class CircuitFails(AlwaysFails):
    calls = 0

    def text(self, query, **kwargs):
        self.__class__.calls += 1
        raise RuntimeError("provider unavailable")


def main() -> None:
    DuckDuckGoSearchClient.reset_circuits()
    with patch("ddgs.DDGS", AutoSuccess):
        AutoSuccess.calls.clear()
        result = DuckDuckGoSearchClient(timeout=2, total_timeout=3).search("时间复杂度", max_results=3)
        assert result.source == "ddgs:auto"
        assert result.results[0].url == "https://example.edu/complexity"
        assert result.results[0].snippet == "真实字段转换"
        assert len(AutoSuccess.calls) == 1

    with patch("ddgs.DDGS", AutoFailsThenBing):
        AutoFailsThenBing.calls.clear()
        result = DuckDuckGoSearchClient(timeout=2, total_timeout=4, proxy="socks5://127.0.0.1:9999").search("数组 链表")
        assert result.source == "ddgs:bing"
        assert [call[2]["backend"] for call in AutoFailsThenBing.calls] == ["auto", "bing"]
        assert AutoFailsThenBing.calls[0][0]["proxy"] == "socks5://127.0.0.1:9999"

    with patch("ddgs.DDGS", AlwaysFails):
        try:
            DuckDuckGoSearchClient(timeout=1, total_timeout=2).search("失败查询")
        except SearchError as exc:
            assert "DDGS search failed" in str(exc)
        else:
            raise AssertionError("all real backends must not fall back to mock results")

    DuckDuckGoSearchClient.reset_circuits()
    with patch("ddgs.DDGS", CircuitFails):
        CircuitFails.calls = 0
        client = DuckDuckGoSearchClient(timeout=1, total_timeout=2)
        for _ in range(3):
            try:
                client.search("circuit test")
            except SearchError:
                pass
        failed_calls = CircuitFails.calls
        try:
            client.search("circuit test")
        except SearchError:
            pass
        assert failed_calls == 9 and CircuitFails.calls == failed_calls
    DuckDuckGoSearchClient.reset_circuits()

    print("search client: PASS")


if __name__ == "__main__":
    main()
