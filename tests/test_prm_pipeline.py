from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

from api_server import app
from prm_pipeline import (
    DEMO_DATASET,
    PRM_DUPLICATE_REVIEWS,
    PRM_MEMORY_PEOPLE,
    _person_from_openai_payload,
    demo_screenshots,
    duplicate_score,
    generate_demo_people,
    run_ingest,
    run_match,
)


class PRMPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old_vision_mode = os.environ.get("PRM_VISION_MODE")
        os.environ["PRM_VISION_MODE"] = "fallback"
        PRM_MEMORY_PEOPLE.clear()
        PRM_DUPLICATE_REVIEWS.clear()

    def tearDown(self) -> None:
        if self._old_vision_mode is None:
            os.environ.pop("PRM_VISION_MODE", None)
        else:
            os.environ["PRM_VISION_MODE"] = self._old_vision_mode

    def test_openai_vision_payload_is_sanitized_to_person_contract(self) -> None:
        person = _person_from_openai_payload(
            {
                "name": "  Ada   Lovelace  ",
                "company": None,
                "role": "AI Researcher",
                "location": "London",
                "interests": [
                    " agents ",
                    "Agents",
                    "evals",
                    "",
                    "developer tools",
                    "privacy",
                    "extra topic",
                ],
                "how_we_met": " LinkedIn profile screenshot ",
                "source": "instagram",
                "unexpected": "ignored",
            },
            "linkedin",
            "uploads/contact.png",
        )

        self.assertEqual(person["name"], "Ada Lovelace")
        self.assertEqual(person["company"], "")
        self.assertEqual(person["source"], "linkedin")
        self.assertEqual(person["interests"], ["agents", "evals", "developer tools", "privacy", "extra topic"])
        self.assertTrue(
            {"id", "name", "company", "role", "location", "interests", "how_we_met", "source", "embedding", "raw_screenshot_ref"}.issubset(person)
        )
        self.assertEqual(person["dataset"], "real")
        self.assertFalse(person["is_demo"])
        self.assertEqual(len(person["source_profiles"]), 1)

    def test_ingest_demo_screenshots_extracts_people(self) -> None:
        result = run_ingest(
            screenshots=demo_screenshots(),
            weave_mode="disabled",
            redis_mode="fake",
        )

        people = result["result"]["people"]
        names = {person["name"] for person in people}

        self.assertEqual(result["weave_mode"], "disabled")
        self.assertGreaterEqual(len(people), 6)
        self.assertIn("Anna Chen", names)
        self.assertEqual(result["result"]["storage"]["redis_status"], "fakeredis")

    def test_generate_demo_people_creates_cluster_friendly_100_person_set(self) -> None:
        people = generate_demo_people()

        self.assertEqual(len(people), 100)
        self.assertEqual(len({person["id"] for person in people}), 100)
        self.assertEqual({person["source"] for person in people}, {"wechat", "linkedin", "whatsapp"})
        self.assertGreaterEqual(len({person["company"] for person in people}), 15)
        self.assertGreaterEqual(len({person["location"] for person in people}), 6)
        self.assertGreaterEqual(len({interest for person in people for interest in person["interests"]}), 25)
        self.assertTrue(all(2 <= len(person["interests"]) <= 4 for person in people))
        self.assertTrue(all(len(person["embedding"]) == 64 for person in people))
        self.assertTrue(all(person["dataset"] == DEMO_DATASET for person in people))
        self.assertTrue(all(person["is_demo"] for person in people))

    def test_seed_endpoint_writes_100_demo_people(self) -> None:
        client = TestClient(app)

        response = client.post(
            "/api/seed",
            json={"size": 100, "redis_mode": "fake"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["people"]), 100)
        self.assertEqual(data["storage"]["count"], 100)
        self.assertEqual(data["storage"]["redis_status"], "fakeredis")
        self.assertTrue(all(person["is_demo"] for person in data["people"]))

    def test_people_endpoint_reads_existing_graph_people(self) -> None:
        client = TestClient(app)

        seed_response = client.post(
            "/api/seed",
            json={"size": 100, "redis_mode": "fake"},
        )
        self.assertEqual(seed_response.status_code, 200)

        response = client.get("/api/prm/people", params={"redis_mode": "fake"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        names = {person["name"] for person in data["people"]}
        self.assertEqual(data["redis_status"], "fakeredis")
        self.assertEqual(len(data["people"]), 100)
        self.assertIn("Anna Chen", names)

    def test_ingest_demo_size_uses_direct_seed_path(self) -> None:
        client = TestClient(app)

        response = client.post(
            "/ingest",
            json={"demo_size": 100, "redis_mode": "fake"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["weave_mode"], "seed")
        self.assertEqual(data["screenshots"], [])
        self.assertEqual(len(data["result"]["people"]), 100)
        self.assertEqual(data["result"]["storage"]["count"], 100)

    def test_ingest_local_endpoint_reads_real_screenshot_directory(self) -> None:
        client = TestClient(app)

        response = client.post(
            "/api/ingest-local",
            json={"weave_mode": "disabled", "redis_mode": "fake"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        people = data["result"]["people"]
        names = {person["name"] for person in people}
        sources = {person["source"] for person in people}

        self.assertEqual(data["weave_mode"], "disabled")
        self.assertEqual(data["local_screenshot_count"], 8)
        self.assertEqual(data["result"]["storage"]["count"], 8)
        self.assertEqual(len(people), 8)
        self.assertIn("Jordan Blake", names)
        self.assertIn("Priya Nair", names)
        self.assertIn("Sophia Laurent", names)
        self.assertEqual(sources, {"wechat", "linkedin", "whatsapp"})
        self.assertTrue(all(person["raw_screenshot_ref"].startswith("anonymized_screenshots/") for person in people))

    def test_ingest_local_accepts_one_safe_relative_path_and_serves_asset(self) -> None:
        client = TestClient(app)

        response = client.post(
            "/api/ingest-local",
            json={
                "paths": ["anonymized_screenshots/04_linkedin_profile_fake.png"],
                "weave_mode": "disabled",
                "redis_mode": "fake",
            },
        )
        asset = client.get("/assets/screenshots/04_linkedin_profile_fake.png")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(asset.status_code, 200)
        data = response.json()
        self.assertEqual(data["local_screenshot_count"], 1)
        self.assertEqual(data["result"]["people"][0]["name"], "Jordan Blake")
        self.assertEqual(data["result"]["people"][0]["source"], "linkedin")

    def test_uploaded_known_screenshot_gets_metadata_without_text_payload(self) -> None:
        client = TestClient(app)

        response = client.post(
            "/ingest",
            json={
                "screenshots": [
                    {
                        "source": "linkedin",
                        "raw_screenshot_ref": "uploads/04_linkedin_profile_fake.png",
                        "image_base64": "data:image/png;base64,ZmFrZQ==",
                    }
                ],
                "weave_mode": "disabled",
                "redis_mode": "fake",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        person = data["result"]["people"][0]
        self.assertEqual(person["name"], "Jordan Blake")
        self.assertEqual(person["company"], "Northstar Labs")
        self.assertEqual(person["raw_screenshot_ref"], "uploads/04_linkedin_profile_fake.png")
        self.assertNotIn("image_base64", data["screenshots"][0])
        self.assertNotIn("image_base64", data["result"]["screenshots"][0])

    def test_upload_appends_to_existing_graph_people(self) -> None:
        client = TestClient(app)
        seed_response = client.post(
            "/api/seed",
            json={"size": 100, "redis_mode": "fake"},
        )
        self.assertEqual(seed_response.status_code, 200)

        response = client.post(
            "/ingest",
            json={
                "screenshots": [
                    {
                        "source": "linkedin",
                        "raw_screenshot_ref": "uploads/04_linkedin_profile_fake.png",
                        "image_base64": "data:image/png;base64,ZmFrZQ==",
                    }
                ],
                "weave_mode": "disabled",
                "redis_mode": "fake",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        names = {person["name"] for person in data["result"]["people"]}
        self.assertEqual(len(data["result"]["people"]), 101)
        self.assertIn("Jordan Blake", names)
        self.assertIn("Anna Chen", names)

    def test_cross_batch_duplicate_auto_merges_same_person(self) -> None:
        client = TestClient(app)

        first = client.post(
            "/ingest",
            json={
                "screenshots": [
                    {
                        "source": "linkedin",
                        "raw_screenshot_ref": "uploads/ada-1.png",
                        "text": "Name: Ada Lovelace\nCompany: Analytical Engines\nRole: AI Researcher\nLocation: London\nInterests: agents, evals\nHow_we_met: LinkedIn profile screenshot",
                    }
                ],
                "weave_mode": "disabled",
                "redis_mode": "fake",
            },
        )
        self.assertEqual(first.status_code, 200)

        second = client.post(
            "/ingest",
            json={
                "screenshots": [
                    {
                        "source": "wechat",
                        "raw_screenshot_ref": "uploads/ada-2.png",
                        "text": "Name: Ada Lovelace\nCompany: Analytical Engines\nRole: AI Researcher\nLocation: London\nInterests: agents, privacy\nHow_we_met: WeChat AI builders group",
                    }
                ],
                "weave_mode": "disabled",
                "redis_mode": "fake",
            },
        )

        self.assertEqual(second.status_code, 200)
        data = second.json()
        people = [person for person in data["result"]["people"] if person["name"] == "Ada Lovelace"]
        self.assertEqual(len(people), 1)
        self.assertEqual(data["result"]["storage"]["duplicate_review_count"], 0)
        self.assertEqual(len(data["result"]["storage"]["merged"]), 1)
        self.assertEqual(len(people[0]["source_profiles"]), 2)
        self.assertIn("privacy", people[0]["interests"])

    def test_medium_confidence_duplicate_goes_to_review_queue(self) -> None:
        client = TestClient(app)

        first = client.post(
            "/ingest",
            json={
                "screenshots": [
                    {
                        "source": "linkedin",
                        "raw_screenshot_ref": "uploads/sam-sf.png",
                        "text": "Name: Sam Lee\nCompany: Northstar Labs\nRole: Product Manager\nLocation: SF\nInterests: AI UX, product strategy\nHow_we_met: LinkedIn profile screenshot",
                    }
                ],
                "weave_mode": "disabled",
                "redis_mode": "fake",
            },
        )
        self.assertEqual(first.status_code, 200)

        second = client.post(
            "/ingest",
            json={
                "screenshots": [
                    {
                        "source": "wechat",
                        "raw_screenshot_ref": "uploads/sam-nyc.png",
                        "text": "Name: Sam Lee\nCompany: Northstar Labs\nRole: Product Manager\nLocation: NYC\nInterests: AI UX, growth\nHow_we_met: WeChat product leaders chat",
                    }
                ],
                "weave_mode": "disabled",
                "redis_mode": "fake",
            },
        )
        reviews_response = client.get("/api/prm/duplicates", params={"redis_mode": "fake"})

        self.assertEqual(second.status_code, 200)
        data = second.json()
        self.assertEqual(len(data["result"]["storage"]["merged"]), 0)
        self.assertEqual(data["result"]["storage"]["duplicate_review_count"], 1)
        self.assertEqual(reviews_response.status_code, 200)
        self.assertEqual(reviews_response.json()["count"], 1)

    def test_duplicate_score_keeps_demo_and_real_records_separate(self) -> None:
        demo_person = generate_demo_people(1)[0]
        real_person = dict(demo_person)
        real_person["id"] = "real-anna"
        real_person["dataset"] = "real"
        real_person["is_demo"] = False
        real_person["raw_screenshot_ref"] = "uploads/anna.png"

        scored = duplicate_score(demo_person, real_person)

        self.assertEqual(scored["score"], 0.0)
        self.assertIn("demo and real records are kept separate", scored["conflicts"])

    def test_export_and_delete_demo_only_preserves_real_contacts(self) -> None:
        client = TestClient(app)
        seed_response = client.post(
            "/api/seed",
            json={"size": 3, "redis_mode": "fake"},
        )
        self.assertEqual(seed_response.status_code, 200)

        upload_response = client.post(
            "/ingest",
            json={
                "screenshots": [
                    {
                        "source": "linkedin",
                        "raw_screenshot_ref": "uploads/real-contact.png",
                        "text": "Name: Real Contact\nCompany: Private Co\nRole: Founder\nLocation: SF\nInterests: startups\nHow_we_met: Private upload",
                    }
                ],
                "weave_mode": "disabled",
                "redis_mode": "fake",
            },
        )
        self.assertEqual(upload_response.status_code, 200)

        export_response = client.get("/api/prm/export", params={"redis_mode": "fake"})
        blocked_delete = client.post("/api/prm/delete-demo", json={"redis_mode": "fake"})
        delete_response = client.post("/api/prm/delete-demo", json={"confirm": True, "redis_mode": "fake"})
        people_response = client.get("/api/prm/people", params={"redis_mode": "fake"})

        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response.json()["person_count"], 4)
        self.assertEqual(blocked_delete.status_code, 400)
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["deleted_count"], 3)
        people = people_response.json()["people"]
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0]["name"], "Real Contact")
        self.assertFalse(people[0]["is_demo"])

    def test_match_endpoint_recommends_gpu_contact(self) -> None:
        client = TestClient(app)
        ingest_response = client.post(
            "/ingest",
            json={"demo": True, "weave_mode": "disabled", "redis_mode": "fake"},
        )
        self.assertEqual(ingest_response.status_code, 200)

        match_response = client.post(
            "/match",
            json={
                "query": "Find someone in SF who knows GPU kernel optimization",
                "weave_mode": "disabled",
                "redis_mode": "fake",
            },
        )

        self.assertEqual(match_response.status_code, 200)
        data = match_response.json()
        recommendations = data["result"]["recommendations"]
        names = [item["person"]["name"] for item in recommendations]

        self.assertGreaterEqual(len(recommendations), 1)
        self.assertIn("Anna Chen", names)
        self.assertTrue(recommendations[0]["draft_message"])

    def test_match_can_seed_demo_data_when_empty(self) -> None:
        result = run_match(
            query="Need Redis vector search advice",
            weave_mode="disabled",
            redis_mode="fake",
        )

        self.assertEqual(result["result"]["recommendations"], [])


if __name__ == "__main__":
    unittest.main()
