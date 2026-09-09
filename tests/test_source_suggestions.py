import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.exceptions import ConflictError, NotFoundError
import app.models  # noqa: F401 — register all tables
from app.models.enums import AccountApprovalStatus, DiscoveryType, UserRole
from app.models.organization import Organization
from app.models.personalization import NewsCategory
from app.models.user import User
from app.schemas.source import SourceApproveRequest
from app.services.llm_client import MockLLMClient
from app.services.source_service import SourceService, filter_suggested_candidates


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


class ApproveSuggestionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            execution_options={"schema_translate_map": {"mint": None}},
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        org = Organization(name="Test", industry="EV")
        self.db.add(org)
        self.db.flush()
        self.admin = User(
            organization_id=org.id,
            email="admin@example.com",
            password_hash="x",
            name="관리자",
            role=UserRole.admin,
            approval_status=AccountApprovalStatus.approved,
            is_active=True,
        )
        self.category = NewsCategory(
            organization_id=org.id,
            name="충전 인프라",
            normalized_name="충전 인프라",
        )
        self.db.add_all([self.admin, self.category])
        self.db.commit()
        self.org_id = org.id
        self.service = SourceService(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _request(self, url: str = "https://good.example/rss") -> SourceApproveRequest:
        return SourceApproveRequest(name="좋은 소스", url=url, source_type="rss", reason="관련 매체")

    def test_approve_creates_source_with_ai_discovered_metadata(self) -> None:
        result = self.service.approve_suggestion(self.org_id, self.category.id, self.admin.id, self._request())
        self.assertEqual(result.discovery_type, DiscoveryType.ai_discovered)
        self.assertEqual(result.approved_by, self.admin.id)
        self.assertIsNotNone(result.approved_at)
        self.assertEqual(result.category_id, self.category.id)
        self.assertEqual(result.category, "충전 인프라")

    def test_approve_rejects_duplicate_url(self) -> None:
        self.service.approve_suggestion(self.org_id, self.category.id, self.admin.id, self._request())
        with self.assertRaises(ConflictError):
            self.service.approve_suggestion(self.org_id, self.category.id, self.admin.id, self._request())

    def test_approve_rejects_inactive_category(self) -> None:
        self.category.is_active = False
        self.db.commit()
        with self.assertRaises(NotFoundError):
            self.service.approve_suggestion(self.org_id, self.category.id, self.admin.id, self._request())

    def test_approve_rejects_other_org_category(self) -> None:
        other_org = Organization(name="Other", industry="EV")
        self.db.add(other_org)
        self.db.commit()
        with self.assertRaises(NotFoundError):
            self.service.approve_suggestion(other_org.id, self.category.id, self.admin.id, self._request())


if __name__ == "__main__":
    unittest.main()
