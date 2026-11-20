# API DOCUMENTATION

## وضعیت
APIهای واقعی باید از کد/Schema استخراج شوند. مسیر یا قرارداد ساختگی را به‌عنوان API موجود ثبت نکنید.

- API style/versioning: `TO_BE_VERIFIED`
- Auth mechanism: `TO_BE_VERIFIED`
- Base URL development: `TO_BE_FILLED`
- OpenAPI/Swagger: `TO_BE_VERIFIED`

## قرارداد هر Endpoint
برای هر endpoint این قالب را تکمیل کنید:

### [METHOD] /path/
- هدف:
- احراز هویت:
- Permission:
- ورودی:
- خروجی موفق:
- خطاهای ممکن:
- Validation:
- Idempotency:
- اثر جانبی:
- تست‌ها:
- وضعیت:

## گروه‌های API مورد انتظار
- Authentication / OTP
- Accounts / Profile
- Catalog / Categories / Brands
- Search / Filters
- Cart
- Pricing / Coupons
- Inventory (مدیریتی)
- Orders
- Payments / Refunds
- Shipping / Tracking
- Invoices
- Loyalty
- Consultations
- Reviews
- CMS / Home
- Notifications (مدیریتی)
- Reports
- RBAC / Audit

## اصول
- پاسخ خطا ساختارمند و پایدار باشد.
- Pagination و فیلترها مستند شوند.
- Permission و مالکیت منابع در Backend بررسی شود.
- قیمت و موجودی ارسالی Frontend قابل اعتماد نیست.
- callback پرداخت باید امضا/اعتبارسنجی و idempotent باشد.
- اطلاعات حساس و داخلی (Batch/Expiration) فقط برای نقش مجاز ارسال شود.
- تغییر قرارداد API باید با نسخه Frontend و تست‌ها هماهنگ شود.

## Endpointهای تأییدشده
| Method | Path | هدف | Auth/Permission | وضعیت |
|---|---|---|---|---|
| — | — | هنوز استخراج نشده | — | TO_BE_VERIFIED |
