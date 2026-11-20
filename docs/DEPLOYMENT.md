# DEPLOYMENT

## وضعیت
جزئیات محیط واقعی باید از مالک/میزبان و Repository تأیید شود. هیچ Secret یا مقدار حساس در این فایل ثبت نشود.

## اطلاعات محیط
| مورد | مقدار/وضعیت |
|---|---|
| Hosting provider | TO_BE_FILLED |
| Domain | در اختیار مالک؛ مقدار دقیق در Secret/محیط امن |
| OS | TO_BE_VERIFIED |
| Python | TO_BE_VERIFIED |
| Django | TO_BE_VERIFIED |
| Database | TO_BE_VERIFIED |
| Frontend build | TO_BE_VERIFIED |
| Web server | TO_BE_VERIFIED |
| Process manager | TO_BE_VERIFIED |
| TLS/SSL | TO_BE_VERIFIED |
| Object/media storage | TO_BE_VERIFIED |
| Backup strategy | TO_BE_FILLED |

## محیط‌ها
- Local development
- Test/CI
- Staging (در صورت امکان)
- Production

## چک‌لیست Production
- [ ] DEBUG=False
- [ ] Secretها از Environment/Secret Manager
- [ ] ALLOWED_HOSTS دقیق
- [ ] HTTPS اجباری
- [ ] Secure cookies و CSRF درست
- [ ] CORS حداقلی
- [ ] دیتابیس Production و دسترسی محدود
- [ ] Migration پس از Backup و بررسی
- [ ] Static/media storage
- [ ] Logging و monitoring
- [ ] Error reporting بدون داده حساس
- [ ] Backup خودکار
- [ ] Restore آزمایش‌شده
- [ ] مدیریت فایل‌های آپلودی
- [ ] اتصال سرویس پیامک و پرداخت با کلیدهای واقعی
- [ ] Callback پرداخت امن و idempotent
- [ ] صفحه‌های حقوقی و اطلاعات مجوز
- [ ] تست Smoke پس از Deploy
- [ ] برنامه Rollback

## عملیات
هر Deploy باید شامل Commit SHA، زمان، Migrationها، نتیجه Smoke test و مسئول اجرا باشد.

## Secret policy
فایل `.env`، کلید Django، رمز دیتابیس، API Key، کلید درگاه و پنل پیامکی نباید Commit شوند. در صورت افشای Secret، صرف حذف از آخرین Commit کافی نیست؛ باید Secret تعویض شود.
