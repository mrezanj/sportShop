
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from orders.models import PROVINCE_CHOICES
from locations.models import Province, City


class Command(BaseCommand):
    help = "Import Iranian provinces and cities from the 1404 reference dataset."

    DATA_FILE = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "iran_divisions_1404_core.json"
    )

    EXPECTED_YEAR = "1404"
    EXPECTED_CITY_COUNT = 1481

    def handle(self, *args, **options):
        if not self.DATA_FILE.is_file():
            raise CommandError(
                f"Dataset file not found: {self.DATA_FILE}"
            )

        try:
            dataset = json.loads(
                self.DATA_FILE.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(
                f"Could not read dataset: {exc}"
            ) from exc

        if str(dataset.get("year")) != self.EXPECTED_YEAR:
            raise CommandError(
                f"Expected dataset year {self.EXPECTED_YEAR}, "
                f"got {dataset.get('year')}."
            )

        if dataset.get("fields") != [
            "id", "parentId", "name", "code", "type"
        ]:
            raise CommandError("Unexpected dataset fields.")

        rows = dataset.get("rows")

        if not isinstance(rows, list):
            raise CommandError("Dataset rows must be a list.")

        records = {}

        for row in rows:
            if not isinstance(row, list) or len(row) != 5:
                raise CommandError("Invalid record found in dataset.")

            record_id = row[0]

            if record_id in records:
                raise CommandError(
                    f"Duplicate record ID found: {record_id}"
                )

            records[record_id] = {
                "id": record_id,
                "parent_id": row[1],
                "name": str(row[2]).strip(),
                "code": str(row[3]).strip(),
                "type": row[4],
            }

        for record in records.values():
            parent_id = record["parent_id"]

            if parent_id is not None and parent_id not in records:
                raise CommandError(
                    f"Missing parent {parent_id} "
                    f"for record {record['id']}."
                )

        province_records = [
            record
            for record in records.values()
            if record["type"] == 1
        ]

        city_records = [
            record
            for record in records.values()
            if record["type"] == 5
        ]

        province_choices = dict(PROVINCE_CHOICES)

        if len(province_records) != len(province_choices):
            raise CommandError(
                "Province count does not match PROVINCE_CHOICES."
            )

        source_provinces = {
            record["name"]: record
            for record in province_records
        }

        if len(source_provinces) != len(province_records):
            raise CommandError(
                "Duplicate province names found in source data."
            )

        missing_provinces = (
            set(province_choices.values())
            - set(source_provinces)
        )

        extra_provinces = (
            set(source_provinces)
            - set(province_choices.values())
        )

        if missing_provinces or extra_provinces:
            raise CommandError(
                "Province names do not match the project choices. "
                f"Missing: {sorted(missing_provinces)}; "
                f"Extra: {sorted(extra_provinces)}"
            )

        if len(city_records) != self.EXPECTED_CITY_COUNT:
            raise CommandError(
                f"Expected {self.EXPECTED_CITY_COUNT} cities, "
                f"found {len(city_records)}."
            )

        prepared_provinces = []
        province_by_source_id = {}

        slug_by_name = {
            name: slug
            for slug, name in PROVINCE_CHOICES
        }

        for source in province_records:
            if not source["code"]:
                raise CommandError(
                    f"Province {source['name']} has no source code."
                )

            province_data = {
                "slug": slug_by_name[source["name"]],
                "name": source["name"],
                "source_code": source["code"],
            }

            prepared_provinces.append(province_data)
            province_by_source_id[source["id"]] = province_data

        prepared_cities = []
        seen_city_codes = set()

        for source in city_records:
            if not source["code"]:
                raise CommandError(
                    f"City {source['name']} has no source code."
                )

            if source["code"] in seen_city_codes:
                raise CommandError(
                    f"Duplicate city code: {source['code']}"
                )

            seen_city_codes.add(source["code"])

            district = records.get(source["parent_id"])

            if district is None or district["type"] != 3:
                raise CommandError(
                    f"Invalid district parent for city {source['name']}."
                )

            county = records.get(district["parent_id"])

            if county is None or county["type"] != 2:
                raise CommandError(
                    f"Invalid county parent for city {source['name']}."
                )

            province = records.get(county["parent_id"])

            if province is None or province["type"] != 1:
                raise CommandError(
                    f"Invalid province parent for city {source['name']}."
                )

            province_data = province_by_source_id.get(province["id"])

            if province_data is None:
                raise CommandError(
                    f"Province mapping not found for city {source['name']}."
                )

            prepared_cities.append({
                "code": source["code"],
                "name": source["name"],
                "county_name": county["name"],
                "district_name": district["name"],
                "province_slug": province_data["slug"],
            })

        created_provinces = 0
        updated_provinces = 0
        created_cities = 0
        updated_cities = 0

        with transaction.atomic():
            province_objects = {}

            for data in prepared_provinces:
                obj, created = Province.objects.update_or_create(
                    slug=data["slug"],
                    defaults={
                        "name": data["name"],
                        "source_code": data["source_code"],
                        "is_active": True,
                    },
                )

                province_objects[data["slug"]] = obj

                if created:
                    created_provinces += 1
                else:
                    updated_provinces += 1

            for data in prepared_cities:
                province = province_objects[data["province_slug"]]

                _, created = City.objects.update_or_create(
                    code=data["code"],
                    defaults={
                        "province": province,
                        "name": data["name"],
                        "county_name": data["county_name"],
                        "district_name": data["district_name"],
                        "is_active": True,
                    },
                )

                if created:
                    created_cities += 1
                else:
                    updated_cities += 1

        self.stdout.write(self.style.SUCCESS(
            "Iranian locations imported successfully."
        ))

        self.stdout.write(
            f"Provinces: {created_provinces} created, "
            f"{updated_provinces} updated."
        )

        self.stdout.write(
            f"Cities: {created_cities} created, "
            f"{updated_cities} updated."
        )
