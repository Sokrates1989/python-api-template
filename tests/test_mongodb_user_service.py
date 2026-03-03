import asyncio
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest import mock

from backend.services.mongodb import user_service as mongo_user_service


def _matches(doc, query):
    for key, expected in query.items():
        if isinstance(expected, dict) and "$ne" in expected:
            if doc.get(key) == expected["$ne"]:
                return False
        else:
            if doc.get(key) != expected:
                return False
    return True


class FakeMongoCollection:
    def __init__(self):
        self.docs = []
        self.indexes = []

    async def create_index(self, field, unique=False, name=None):
        self.indexes.append((field, unique, name))
        return name or field

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                if projection:
                    included = {}
                    for key, include in projection.items():
                        if include and key in doc:
                            included[key] = doc[key]
                    return included
                return deepcopy(doc)
        return None

    async def insert_one(self, payload):
        doc = deepcopy(payload)
        doc["_id"] = str(len(self.docs) + 1)
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc["_id"])

    async def find_one_and_update(self, query, update, return_document=None):
        for idx, doc in enumerate(self.docs):
            if _matches(doc, query):
                updated = deepcopy(doc)
                for key, value in update.get("$set", {}).items():
                    updated[key] = value
                for key, inc in update.get("$inc", {}).items():
                    updated[key] = int(updated.get(key, 0)) + int(inc)
                self.docs[idx] = updated
                return deepcopy(updated)
        return None


def _build_service(collection):
    service = mongo_user_service.UserService.__new__(mongo_user_service.UserService)
    service.collection = collection
    service._indexes_initialized = False
    return service


class MongoUserServiceTests(unittest.TestCase):
    def test_create_get_and_update_user(self):
        with mock.patch.object(
            mongo_user_service,
            "ReturnDocument",
            SimpleNamespace(AFTER="after"),
        ):
            service = _build_service(FakeMongoCollection())

            created = asyncio.run(
                service.create_user(
                    user_id="u-1",
                    email="user1@example.com",
                    username=None,
                    first_name="U",
                    last_name="One",
                )
            )
            self.assertEqual(created["status"], "success")
            self.assertEqual(created["data"]["username"], "user1")
            self.assertEqual(created["data"]["version"], 1)

            fetched = asyncio.run(service.get_user("u-1"))
            self.assertEqual(fetched["status"], "success")
            self.assertEqual(fetched["data"]["email"], "user1@example.com")

            updated = asyncio.run(
                service.update_user(
                    user_id="u-1",
                    email="user1+new@example.com",
                    username="user1-new",
                    first_name="User",
                    last_name="One",
                )
            )
            self.assertEqual(updated["status"], "success")
            self.assertEqual(updated["data"]["version"], 2)
            self.assertEqual(updated["data"]["email"], "user1+new@example.com")

    def test_duplicate_email_and_username_detection(self):
        with mock.patch.object(
            mongo_user_service,
            "ReturnDocument",
            SimpleNamespace(AFTER="after"),
        ):
            service = _build_service(FakeMongoCollection())

            first = asyncio.run(
                service.create_user("u-1", "user1@example.com", "user1", None, None)
            )
            self.assertEqual(first["status"], "success")

            duplicate_email = asyncio.run(
                service.create_user("u-2", "user1@example.com", "user2", None, None)
            )
            self.assertEqual(duplicate_email["status"], "error")
            self.assertIn("already registered", duplicate_email["message"])

            duplicate_username = asyncio.run(
                service.create_user("u-3", "user3@example.com", "user1", None, None)
            )
            self.assertEqual(duplicate_username["status"], "error")
            self.assertIn("already in use", duplicate_username["message"])
