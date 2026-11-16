import json
import logging
import os
import time
from collections.abc import Callable
from typing import TypeVar
from urllib.error import URLError
from urllib.request import Request, urlopen

import psycopg

LOG = logging.getLogger("pet-import")
ATTEMPTS = 5
TIMEOUT = 10
T = TypeVar("T")
Pet = tuple[int, str, str, str, int]


def retry(action: Callable[[], T], errors: tuple[type[Exception], ...]) -> T:
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return action()
        except errors as exc:
            if attempt == ATTEMPTS:
                raise
            delay = min(2 ** (attempt - 1), 8)
            LOG.warning("Attempt %s/%s failed: %s; retrying in %ss", attempt, ATTEMPTS, exc, delay)
            time.sleep(delay)


def fetch_pets() -> list[object]:
    url = os.environ.get("PETSTORE_URL", "https://petstore.swagger.io/v2").rstrip("/")
    request = Request(url + "/pet/findByStatus?status=available", headers={"Accept": "application/json"})
    with urlopen(request, timeout=TIMEOUT) as response:
        data = json.load(response)
    if not isinstance(data, list):
        raise ValueError("Petstore response must be a JSON array")
    return data


def select_pets(data: list[object], prefix: str) -> list[Pet]:
    selected: list[Pet] = []
    for pet in data:
        if not isinstance(pet, dict):
            LOG.warning("Skipping non-object pet")
            continue
        name, pet_id = pet.get("name"), pet.get("id")
        if not isinstance(name, str) or not name.startswith(prefix):
            continue
        if type(pet_id) is not int or not -(2**63) <= pet_id < 2**63 or pet.get("status") != "available":
            LOG.warning("Skipping matching pet with invalid id or status: %r", pet_id)
            continue
        category = pet.get("category")
        category_name = category.get("name") if isinstance(category, dict) else None
        if not isinstance(category_name, str) or not category_name:
            category_name = "unknown"
        selected.append((pet_id, name, "available", category_name, len(name)))
    return selected


def store_pets(pets: list[Pet]) -> None:
    with psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ.get("POSTGRES_DB", "petstore"),
        user=os.environ.get("POSTGRES_USER", "petstore"),
        password=os.environ.get("POSTGRES_PASSWORD", "petstore"),
        connect_timeout=TIMEOUT,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""CREATE TABLE IF NOT EXISTS pets (
                id BIGINT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
                pet_category TEXT NOT NULL, name_character_count INTEGER NOT NULL
            )""")
            cursor.executemany("""INSERT INTO pets (id, name, status, pet_category, name_character_count)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = EXCLUDED.status,
                pet_category = EXCLUDED.pet_category, name_character_count = EXCLUDED.name_character_count
            """, pets)


def main() -> None:
    prefix = os.environ.get("PET_NAME_PREFIX") or "M"
    LOG.info("Fetching available pets with names starting with %r", prefix)
    pets = select_pets(retry(fetch_pets, (URLError, TimeoutError, OSError, ValueError)), prefix)
    retry(lambda: store_pets(pets), (psycopg.OperationalError, psycopg.InterfaceError))
    for _, name, _, category, count in pets:
        print(f"The {category} {name} has {count} characters")
    LOG.info("Stored %s matching pets", len(pets))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        main()
    except Exception as exc:
        LOG.error("Import failed: %s", exc)
        raise SystemExit(1)
