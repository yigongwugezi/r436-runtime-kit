"""Test DeepSeek built-in web search with deepseek-v4-flash."""
import json
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")

API_KEY = "sk-46eab1eaef73426680f198427bf7094a"
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-flash"

def test_search(search_enabled: bool):
    label = "[search=true]" if search_enabled else "[no search param]"
    print(f"\n{'='*60}")
    print(f"Test: {label}")
    print(f"{'='*60}")

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "What is today's date? Any major news recently?"}
        ],
        "stream": False,
        "max_tokens": 500,
    }
    if search_enabled:
        payload["search"] = True

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=f"{BASE_URL}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        print("SUCCESS")
        print(f"model: {body.get('model')}")
        print(f"Response:\n{content[:800]}")

        body_str = json.dumps(body, ensure_ascii=False)
        if "search_results" in body_str:
            print("\n>>> search_results field FOUND in response!")
            sr = body.get("search_results", "")
            print(f"search_results: {json.dumps(sr, ensure_ascii=False)[:500]}")
        else:
            print("\n>>> No 'search_results' field in response body")

        realtime_hints = ["2025", "2026", "today", "currently", "latest", "news", "recent"]
        found = [h for h in realtime_hints if h.lower() in content.lower()]
        if found:
            print(f">>> Real-time keywords found: {found}")
        else:
            print(">>> No obvious real-time keywords (inconclusive)")

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")[:500]
        print(f"HTTP {e.code}: {err_body}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_search(search_enabled=True)
    test_search(search_enabled=False)
