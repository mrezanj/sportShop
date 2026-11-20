# DATABASE SCHEMA

## وضعیت
این سند تا زمان بررسی مدل‌های واقعی `TO_BE_VERIFIED` است. مدل پیشنهادی را بدون تطبیق با کد موجود پیاده‌سازی نکنید.

## قواعد طراحی
- نام مدل و فیلد واقعی همراه نوع، nullability، default و constraint ثبت شود.
- روابط، cardinality و on_delete مشخص شوند.
- قیمت/نام/کد محصول سفارش باید Snapshot شود تا تغییرات بعدی کاتالوگ فاکتور قبلی را عوض نکند.
- عملیات مالی و موجودی قابل حذف فیزیکی نباشند؛ از وضعیت/رویداد و audit استفاده شود.
- برای موجودی هم‌زمان، تراکنش و قفل ردیف/استراتژی اتمیک طراحی شود.
- SKU یکتا و شناسه‌های خارجی دارای constraint باشند.

## موجودیت‌های دامنه مورد انتظار
| حوزه | موجودیت پیشنهادی | توضیح |
|---|---|---|
| کاربران | User, CustomerProfile, Address | هویت و اطلاعات مشتری |
| احراز هویت | OTPChallenge | کد hash‌شده، انقضا، تعداد تلاش |
| کاتالوگ | Product, ProductVariant, Category, Brand | محصول و تنوع |
| ویژگی‌ها | Attribute, AttributeValue / VariantAttribute | ویژگی منعطف |
| رسانه | ProductImage | تصاویر |
| انبار | Warehouse, Stock, StockMovement | با یک انبار فعال در Scope |
| بچ | InventoryBatch | شماره بچ و انقضا داخلی |
| رزرو | StockReservation, ReservationItem | رزرو موقت سفارش |
| قیمت | Price / Variant price fields | قیمت جاری؛ تاریخچه قیمت لازم نیست |
| تخفیف | Discount, Coupon, DiscountRule | قواعد تخفیف |
| سبد | Cart, CartItem | داده موقت سبد |
| سفارش | Order, OrderItem, OrderStatusHistory | Snapshot و تاریخچه |
| پرداخت | Payment, PaymentAttempt, Refund | مستقل از Order |
| ارسال | ShippingMethod, ShippingRate, Shipment | مرسوله و رهگیری |
| بسته‌بندی | PackagingRule / OrderPackagingItem | هزینه ویژه |
| فاکتور | Invoice, InvoiceLine | Snapshot مالی |
| وفاداری | LoyaltyAccount, PointTransaction, CustomerTier | امتیاز و انقضا |
| مشاوره | Consultant, AvailabilitySlot, ConsultationBooking | زمان‌بندی و رزرو |
| اعلان | NotificationTemplate, NotificationLog | پیامک و وضعیت |
| مدیریت | Role, Permission mapping, AuditLog | دسترسی و ردپا |

## جدول مدل‌های واقعی
| App | Model | فیلدها و نوع | روابط/Constraints | وضعیت |
|---|---|---|---|---|
| TO_BE_FILLED | TO_BE_FILLED | TO_BE_FILLED | TO_BE_FILLED | TO_BE_VERIFIED |

## Migrationها
| تاریخ | Migration | تغییر | داده حساس/Backfill | Rollback |
|---|---|---|---|---|
| — | — | — | — | — |

## پرسش‌های طراحی باز
- موجودی به تفکیک Batch نگهداری شود یا فقط جمع SKU؟ (پیشنهاد: بچ‌محور برای مکمل‌ها)
- FIFO/FEFO برای برداشت لازم است؟
- نگهداری قیمت در OrderItem چگونه Snapshot شود؟
- رزرو موجودی با انقضای پرداخت چگونه زمان‌بندی و آزاد شود؟
- مالیات و گرد کردن مبالغ در چه سطحی اعمال شود؟
