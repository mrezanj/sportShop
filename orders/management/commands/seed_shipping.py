from django.core.management.base import BaseCommand, CommandError

from locations.models import City
from orders.models import ShippingMethod, ShippingRate, PROVINCE_CHOICES


class Command(BaseCommand):
    help = "Seed shipping methods and rates"

    def handle(self, *args, **options):
        hamadan_city = (
            City.objects.select_related("province")
            .filter(
                province__slug="hamedan",
                name="همدان",
                is_active=True,
                province__is_active=True,
            )
            .order_by("id")
            .first()
        )
        if hamadan_city is None:
            raise CommandError(
                "شهر فعال همدان پیدا نشد. ابتدا اطلاعات استان‌ها و شهرها را وارد کنید."
            )

        post, _ = ShippingMethod.objects.get_or_create(
            slug="post",
            defaults={
                "name": "پست پیشتاز",
                "description": "ارسال به سراسر کشور - ۳ تا ۵ روز کاری",
                "order": 1,
            },
        )
        tipax, _ = ShippingMethod.objects.get_or_create(
            slug="tipax",
            defaults={
                "name": "تیپاکس",
                "description": "ارسال سریع - ۱ تا ۳ روز کاری",
                "order": 2,
            },
        )
        motor, _ = ShippingMethod.objects.update_or_create(
            slug="motorcycle",
            defaults={
                "name": "پیک موتوری (فقط شهر همدان)",
                "description": "تحویل در همان روز - فقط شهر همدان",
                "order": 3,
                "restricted_province": "hamedan",
                "restricted_city": hamadan_city,
            },
        )

        # Post rates: tehran=50k, hamedan=60k, others=70k
        for slug, name in PROVINCE_CHOICES:
            if slug == "tehran":
                cost = 50_000
            elif slug == "hamedan":
                cost = 60_000
            else:
                cost = 70_000
            ShippingRate.objects.update_or_create(
                method=post, province=slug, defaults={"cost": cost}
            )

        # Tipax rates: tehran=80k, hamedan=90k, others=100k
        for slug, name in PROVINCE_CHOICES:
            if slug == "tehran":
                cost = 80_000
            elif slug == "hamedan":
                cost = 90_000
            else:
                cost = 100_000
            ShippingRate.objects.update_or_create(
                method=tipax, province=slug, defaults={"cost": cost}
            )

        # Motorcycle: only the city of Hamadan, not the entire province.
        ShippingRate.objects.update_or_create(
            method=motor, province="hamedan", defaults={"cost": 40_000}
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Shipping seeded: {ShippingMethod.objects.count()} methods, "
                f"{ShippingRate.objects.count()} rates"
            )
        )
