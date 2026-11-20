# ARCHITECTURE

## وضعیت
این سند قالب معماری است. تا زمان بررسی Repository، هیچ تکنولوژی/ماژولی را قطعی فرض نکنید.

- بررسی در تاریخ: `TO_BE_FILLED`
- Branch/Commit: `TO_BE_FILLED`
- Backend stack واقعی: `TO_BE_FILLED`
- Frontend stack واقعی: `TO_BE_FILLED`
- Database واقعی: `TO_BE_FILLED`

## اصول معماری هدف
- مرزبندی روشن ماژول‌ها و مسئولیت‌ها
- منطق تجاری مستقل از لایه HTTP/UI تا حد امکان
- تراکنش اتمیک برای سفارش، پرداخت و موجودی
- Permission سمت سرور
- Adapter برای سرویس‌های خارجی
- ثبت رویدادهای حساس و Audit Trail
- تست‌پذیری و قابلیت مشاهده خطاها
- جلوگیری از وابستگی دوری بین اپلیکیشن‌ها

## ماژول‌های دامنه پیشنهادی
| ماژول | مسئولیت | وابستگی‌های اصلی |
|---|---|---|
| accounts | کاربر، OTP، پروفایل، نقش | — |
| catalog | محصول، تنوع، SKU، برند، دسته | — |
| inventory | انبار، بچ، حرکت موجودی، رزرو | catalog |
| pricing | قیمت، قوانین قیمت، تخفیف | catalog |
| cart | سبد خرید و اعتبارسنجی | catalog, pricing |
| orders | سفارش، Snapshot، وضعیت | accounts, cart, inventory, pricing |
| payments | پرداخت و بازپرداخت | orders |
| shipping | تعرفه، بسته‌بندی، مرسوله | orders, catalog |
| billing | فاکتور و مالیات | orders, shipping |
| loyalty | امتیاز و سطح مشتری | accounts, orders |
| consultation | مشاور، زمان‌بندی، رزرو | accounts |
| notifications | پیامک و قالب‌ها | accounts, orders |
| cms | بنر و محتوای صفحات | — |
| reporting | گزارش‌های مدیریتی | ماژول‌های دامنه |
| audit | ثبت عملیات مدیریتی | ماژول‌های حساس |

این تقسیم‌بندی پیشنهاد اولیه است و باید با ساختار فعلی Repository تطبیق داده شود؛ الزام به ساخت دقیقاً همین تعداد Django app وجود ندارد.

## جریان‌های حساس
### ثبت سفارش
Cart validation → price revalidation → customer confirmation if changed → stock reservation → order creation → payment initiation.

### پرداخت موفق
Verify gateway callback → idempotency check → mark payment success → confirm order transition → finalize reservation/stock movement → issue invoice/notifications.

### پرداخت ناموفق/انقضای رزرو
ثبت نتیجه → آزادسازی رزرو مطابق سیاست → حفظ تاریخچه → امکان تلاش مجدد طبق قواعد سفارش.

### مرجوعی
ثبت درخواست → بررسی مدیر → دریافت کالا → کنترل وضعیت کالا → تصمیم بازپرداخت → ثبت حرکت انبار و Refund.

## تصمیمات فنی لازم
در `DECISION_LOG.md` ثبت شوند:
- monolith یا modular monolith
- task queue و scheduler موردنیاز
- روش cache
- روش فایل/تصویر
- روش جستجو
- استراتژی idempotency
- سیاست رزرو و انقضای موجودی
- Audit log و logging
- معماری Permission

## امنیت
- Secret فقط در environment/secret manager
- DEBUG خاموش در Production
- ALLOWED_HOSTS محدود
- HTTPS و cookie امن
- CSRF/CORS محدود و دقیق
- rate limit برای OTP و endpointهای حساس
- hash امن OTP و زمان انقضا
- کنترل دسترسی به داده‌های کاربر
- اعتبارسنجی فایل آپلودی
- پشتیبان‌گیری و آزمون بازیابی
