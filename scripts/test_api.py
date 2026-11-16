"""Live contract checks. These create and delete a uniquely identified public pet."""
import json
import os
import unittest
import uuid
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from jsonschema import Draft4Validator

BASE = os.environ.get("PETSTORE_URL", "https://petstore.swagger.io/v2").rstrip("/")


def request(method, path, body=None, content_type=None):
    headers = {"Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    req = Request(BASE + path, data=body, headers=headers, method=method)
    try:
        response = urlopen(req, timeout=15)
    except HTTPError as exc:
        response = exc
    with response:
        raw = response.read()
        return response.status, json.loads(raw) if raw else None


class PetstoreAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        status, cls.spec = request("GET", "/swagger.json")
        if status != 200:
            raise RuntimeError(f"Unable to load OpenAPI specification: HTTP {status}")

    def assert_schema(self, value, schema):
        validator = Draft4Validator({"definitions": self.spec["definitions"], **schema})
        errors = list(validator.iter_errors(value))
        self.assertFalse(errors, "; ".join(error.message for error in errors[:5]))

    def test_pet_lifecycle_and_search(self):
        # Stay within JavaScript's safe integer range on the shared public API.
        pet_id = 1_000_000_000_000 + uuid.uuid4().int % 8_000_000_000_000_000
        tag = "qa-" + uuid.uuid4().hex
        pet = {"id": pet_id, "name": "M-test-" + tag, "photoUrls": [],
               "status": "available", "category": {"name": "test"}, "tags": [{"name": tag}]}

        def cleanup():
            try:
                request("DELETE", f"/pet/{pet_id}")
            except Exception as exc:
                print(f"Cleanup failed for pet {pet_id}: {exc}")

        self.addCleanup(cleanup)
        status, created = request("POST", "/pet", json.dumps(pet).encode(), "application/json")
        self.assertEqual(status, 200)
        self.assert_schema(created, {"$ref": "#/definitions/Pet"})
        self.assertEqual(created["id"], pet_id)

        status, found = request("GET", f"/pet/{pet_id}")
        self.assertEqual(status, 200)
        self.assert_schema(found, {"$ref": "#/definitions/Pet"})
        self.assertEqual(found["name"], pet["name"])

        pet["name"] += "-updated"
        status, updated = request("PUT", "/pet", json.dumps(pet).encode(), "application/json")
        self.assertEqual(status, 200)
        self.assert_schema(updated, {"$ref": "#/definitions/Pet"})
        self.assertEqual(updated["name"], pet["name"])

        status, form_result = request("POST", f"/pet/{pet_id}",
                                      urlencode({"name": pet["name"], "status": "available"}).encode(),
                                      "application/x-www-form-urlencoded")
        self.assertEqual(status, 200)
        self.assert_schema(form_result, {"$ref": "#/definitions/ApiResponse"})

        boundary = "petstore-" + uuid.uuid4().hex
        image = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.txt\"\r\n"
                 f"Content-Type: text/plain\r\n\r\ntest upload\r\n--{boundary}--\r\n").encode()
        status, upload = request("POST", f"/pet/{pet_id}/uploadImage", image,
                                 f"multipart/form-data; boundary={boundary}")
        self.assertEqual(status, 200)
        self.assert_schema(upload, {"$ref": "#/definitions/ApiResponse"})

        for path in ("/pet/findByStatus?status=available", "/pet/findByTags?" + urlencode({"tags": tag})):
            with self.subTest(path=path):
                status, results = request("GET", path)
                self.assertEqual(status, 200)
                self.assert_schema(results, {"type": "array"})
                matches = [item for item in results if isinstance(item, dict) and item.get("id") == pet_id]
                self.assertEqual(len(matches), 1)
                self.assert_schema(matches[0], {"$ref": "#/definitions/Pet"})

        status, deleted = request("DELETE", f"/pet/{pet_id}")
        self.assertEqual(status, 200)
        self.assert_schema(deleted, {"$ref": "#/definitions/ApiResponse"})
        status, _ = request("GET", f"/pet/{pet_id}")
        self.assertEqual(status, 404)

    def test_invalid_id(self):
        status, _ = request("GET", "/pet/not-an-integer")
        # The public server returns 404 for this route although the spec documents 400.
        self.assertIn(status, (400, 404))

    def test_invalid_json(self):
        status, _ = request("POST", "/pet", b"{", "application/json")
        self.assertIn(status, (400, 405))


if __name__ == "__main__":
    unittest.main()
