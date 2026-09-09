import unittest

from app.services.llm_client import MockLLMClient
from app.services.source_service import filter_suggested_candidates


class MockLLMSuggestSourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MockLLMClient()

    def test_returns_requested_count(self) -> None:
        candidates = self.client.suggest_sources(
            "충전 인프라", industry="EV", count=3, existing_urls=[]
        )
        self.assertEqual(len(candidates), 3)
        for c in candidates:
            self.assertTrue(c["url"].startswith("https://"))
            self.assertEqual(c["source_type"], "rss")
            self.assertIn("충전 인프라", c["name"])

    def test_excludes_existing_urls(self) -> None:
        first = self.client.suggest_sources(
            "정책/규제", industry="EV", count=2, existing_urls=[]
        )
        existing = [first[0]["url"]]
        second = self.client.suggest_sources(
            "정책/규제", industry="EV", count=2, existing_urls=existing
        )
        urls = {c["url"] for c in second}
        self.assertNotIn(existing[0], urls)

    def test_zero_count_returns_empty(self) -> None:
        candidates = self.client.suggest_sources(
            "기술", industry="EV", count=0, existing_urls=[]
        )
        self.assertEqual(candidates, [])


class FilterSuggestedCandidatesTest(unittest.TestCase):
    def test_drops_malformed_url(self) -> None:
        raw = [
            {"name": "A", "url": "not-a-url", "source_type": "rss", "reason": "x"},
            {"name": "B", "url": "https://good.example/rss", "source_type": "rss", "reason": "x"},
        ]
        result = filter_suggested_candidates(raw, existing_urls=[])
        self.assertEqual([c.name for c in result], ["B"])

    def test_drops_duplicate_of_existing_url(self) -> None:
        raw = [{"name": "A", "url": "https://dup.example/rss", "source_type": "rss", "reason": "x"}]
        result = filter_suggested_candidates(raw, existing_urls=["https://dup.example/rss"])
        self.assertEqual(result, [])

    def test_drops_candidate_missing_required_field(self) -> None:
        raw = [{"name": "A", "url": "https://good.example/rss", "source_type": "rss"}]
        result = filter_suggested_candidates(raw, existing_urls=[])
        self.assertEqual(result, [])

    def test_rejects_non_http_scheme(self) -> None:
        raw = [{"name": "A", "url": "ftp://bad.example/feed", "source_type": "rss", "reason": "x"}]
        result = filter_suggested_candidates(raw, existing_urls=[])
        self.assertEqual(result, [])

    def test_keeps_valid_unique_candidate(self) -> None:
        raw = [{"name": "A", "url": "https://good.example/rss", "source_type": "rss", "reason": "관련 매체"}]
        result = filter_suggested_candidates(raw, existing_urls=[])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].url, "https://good.example/rss")


if __name__ == "__main__":
    unittest.main()
