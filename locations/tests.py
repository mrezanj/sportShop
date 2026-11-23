
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Province, City


class LocationAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hamedan = Province.objects.create(
            slug="hamedan",
            name="همدان",
            source_code="13",
        )

        cls.tehran = Province.objects.create(
            slug="tehran",
            name="تهران",
            source_code="23",
        )

        cls.inactive_province = Province.objects.create(
            slug="inactive",
            name="استان غیرفعال",
            source_code="99",
            is_active=False,
        )

        cls.hamedan_city = City.objects.create(
            province=cls.hamedan,
            code="1475",
            name="همدان",
            county_name="همدان",
            district_name="مرکزی",
        )

        cls.first_duplicate_city = City.objects.create(
            province=cls.hamedan,
            code="9001",
            name="شهر نمونه",
            county_name="شهرستان اول",
            district_name="بخش اول",
        )

        cls.second_duplicate_city = City.objects.create(
            province=cls.hamedan,
            code="9002",
            name="شهر نمونه",
            county_name="شهرستان دوم",
            district_name="بخش دوم",
        )

        cls.tehran_city = City.objects.create(
            province=cls.tehran,
            code="9003",
            name="شهر تهران",
            county_name="تهران",
            district_name="مرکزی",
        )

        cls.inactive_city = City.objects.create(
            province=cls.hamedan,
            code="9004",
            name="شهر غیرفعال",
            county_name="همدان",
            district_name="مرکزی",
            is_active=False,
        )

        cls.client = APIClient()

    def test_list_provinces_returns_active_provinces(self):
        response = self.client.get("/api/locations/provinces/")

        self.assertEqual(response.status_code, 200)

        slugs = {
            province["slug"]
            for province in response.data
        }

        self.assertIn("hamedan", slugs)
        self.assertIn("tehran", slugs)
        self.assertNotIn("inactive", slugs)

    def test_list_cities_requires_province_parameter(self):
        response = self.client.get("/api/locations/cities/")

        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.data)

    def test_list_cities_returns_only_selected_province_cities(self):
        response = self.client.get(
            "/api/locations/cities/",
            {"province": "hamedan"},
        )

        self.assertEqual(response.status_code, 200)

        codes = {
            city["code"]
            for city in response.data
        }

        self.assertIn("1475", codes)
        self.assertIn("9001", codes)
        self.assertIn("9002", codes)
        self.assertNotIn("9003", codes)
        self.assertNotIn("9004", codes)

    def test_list_cities_includes_county_and_district(self):
        response = self.client.get(
            "/api/locations/cities/",
            {"province": "hamedan"},
        )

        self.assertEqual(response.status_code, 200)

        city = next(
            item
            for item in response.data
            if item["code"] == "1475"
        )

        self.assertEqual(city["name"], "همدان")
        self.assertEqual(city["county_name"], "همدان")
        self.assertEqual(city["district_name"], "مرکزی")

    def test_duplicate_city_names_are_returned_separately(self):
        response = self.client.get(
            "/api/locations/cities/",
            {"province": "hamedan"},
        )

        self.assertEqual(response.status_code, 200)

        duplicate_cities = [
            city
            for city in response.data
            if city["name"] == "شهر نمونه"
        ]

        self.assertEqual(len(duplicate_cities), 2)

        self.assertEqual(
            {city["county_name"] for city in duplicate_cities},
            {"شهرستان اول", "شهرستان دوم"},
        )

        self.assertEqual(
            {city["code"] for city in duplicate_cities},
            {"9001", "9002"},
        )

    def test_list_cities_returns_404_for_unknown_province(self):
        response = self.client.get(
            "/api/locations/cities/",
            {"province": "invalid"},
        )

        self.assertEqual(response.status_code, 404)

    def test_list_cities_returns_404_for_inactive_province(self):
        response = self.client.get(
            "/api/locations/cities/",
            {"province": "inactive"},
        )

        self.assertEqual(response.status_code, 404)

    def test_list_cities_does_not_return_inactive_cities(self):
        response = self.client.get(
            "/api/locations/cities/",
            {"province": "hamedan"},
        )

        self.assertEqual(response.status_code, 200)

        codes = {
            city["code"]
            for city in response.data
        }

        self.assertNotIn("9004", codes)
