
'use client';

import { Suspense, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import { createReturnRequest, fetchInvoice, fetchOrderDetail, fetchReturnRequests, type OrderDetail, type ReturnRequestRecord } from '@/lib/api';

function formatOrderDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('fa-IR', {
    timeZone: 'Asia/Tehran',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-800 border-amber-200',
  paid: 'bg-blue-100 text-blue-800 border-blue-200',
  processing: 'bg-purple-100 text-purple-800 border-purple-200',
  shipped: 'bg-indigo-100 text-indigo-800 border-indigo-200',
  delivered: 'bg-green-100 text-green-800 border-green-200',
  cancelled: 'bg-red-100 text-red-800 border-red-200',
  discrepancy: 'bg-orange-100 text-orange-800 border-orange-200',
};

export default function OrderDetailPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-gray-500">
          در حال بارگذاری...
        </div>
      }
    >
      <OrderDetailContent />
    </Suspense>
  );
}

function OrderDetailContent() {
  const params = useParams();
  const router = useRouter();
  const orderNumber = params.orderNumber as string;
  const { isAuthenticated, loading: authLoading, token } = useAuth();

  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [invoiceAvailable, setInvoiceAvailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [returnReason, setReturnReason] = useState('');
  const [returnQuantities, setReturnQuantities] = useState<Record<number, number>>({});
  const [returnQuantityInputs, setReturnQuantityInputs] = useState<Record<number, string>>({});
  const [invalidReturnQuantities, setInvalidReturnQuantities] = useState<Record<number, boolean>>({});
  const [returnRequest, setReturnRequest] = useState<ReturnRequestRecord | null>(null);
  const [returnSubmitting, setReturnSubmitting] = useState(false);
  const [returnMessage, setReturnMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push(`/login?returnTo=/account/orders/${orderNumber}`);
    }
  }, [authLoading, isAuthenticated, router, orderNumber]);

  useEffect(() => {
    if (!token || !orderNumber) return;

    fetchOrderDetail(orderNumber, token)
      .then(async (result) => {
        setOrder(result);
        if (['paid', 'processing', 'shipped', 'delivered', 'discrepancy'].includes(result.status)) {
          try {
            await fetchInvoice(result.order_number, token);
            setInvoiceAvailable(true);
          } catch {
            // Older paid orders may predate invoice issuance.
          }
        }
        try {
          const requests = await fetchReturnRequests(token);
          setReturnRequest(requests.find((item) => item.order_id === result.id && ["requested", "approved", "received"].includes(item.status)) ?? null);
        } catch {
          // The order remains usable if return history cannot be loaded.
        }
      })
      .catch(() => setError('سفارش یافت نشد.'))
      .finally(() => setLoading(false));
  }, [token, orderNumber]);

  async function submitReturnRequest() {
    if (!token || !order) return;
    if (Object.values(invalidReturnQuantities).some(Boolean)) {
      setReturnMessage('تعداد مرجوعی باید فقط یک عدد صحیح باشد.');
      return;
    }
    const items = order.items
      .map((item) => ({ order_item_id: item.id, quantity: returnQuantities[item.id] || 0 }))
      .filter((item) => item.quantity > 0);
    if (!returnReason.trim() || items.length === 0) {
      setReturnMessage('علت مرجوعی و حداقل یک قلم با تعداد معتبر را وارد کنید.');
      return;
    }
    setReturnSubmitting(true);
    setReturnMessage(null);
    try {
      const result = await createReturnRequest(order.order_number, returnReason, items, token);
      setReturnRequest(result);
      setReturnMessage('درخواست مرجوعی با موفقیت ثبت شد و در انتظار بررسی است.');
      setReturnReason('');
      setReturnQuantities({});
      setReturnQuantityInputs({});
      setInvalidReturnQuantities({});
    } catch (err) {
      setReturnMessage(err instanceof Error ? err.message : 'ثبت درخواست ناموفق بود.');
    } finally {
      setReturnSubmitting(false);
    }
  }

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500">
        در حال بارگذاری...
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4" dir="rtl">
        <div className="text-center">
          <p className="text-gray-700 mb-4">
            {error || 'سفارش یافت نشد.'}
          </p>
          <Link
            href="/account"
            className="text-pink-800 hover:text-pink-900 font-medium"
          >
            بازگشت به سفارش‌ها
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-page" dir="rtl">
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <nav className="text-sm text-gray-500 mb-6">
          <Link href="/account" className="hover:text-pink-800">
            سفارش‌های من
          </Link>
          <span className="mx-2">/</span>
          <span className="text-gray-800" dir="ltr">
            {order.order_number}
          </span>
        </nav>

        {/* Header */}
        <div className="mb-6 rounded-2xl border border-pink-200 bg-gradient-to-l from-pink-200/80 via-rose-100 to-pink-100 p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs text-gray-600 mb-1">شماره سفارش</p>
              <p className="text-lg font-bold text-gray-900" dir="ltr">
                {order.order_number}
              </p>
            </div>
            <span
              className={`text-sm px-4 py-1.5 rounded-full border ${
                STATUS_COLORS[order.status] ??
                'bg-gray-100 text-gray-800 border-gray-200'
              }`}
            >
              {order.status_display}
            </span>
          </div>
          <p className="text-xs text-gray-600 mt-3">
            تاریخ ثبت:{' '}
            {formatOrderDate(order.created_at)}
          </p>

          {order.tracking_code && (
            <div className="mt-3 bg-white border border-indigo-200 rounded-lg p-3 text-sm text-indigo-800">
              کد رهگیری:{' '}
              <span className="font-bold" dir="ltr">
                {order.tracking_code}
              </span>
            </div>
          )}
        </div>

        {/* Pending payment banner */}
        {order.status === 'pending' && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div>
              <p className="font-semibold text-amber-900">
                این سفارش در انتظار پرداخت است
              </p>
              <p className="text-sm text-amber-800 mt-1">
                برای تکمیل خرید، پرداخت را انجام دهید.
              </p>
            </div>
            <Link
              href={`/checkout/payment?order=${order.order_number}`}
              className="bg-pink-800 hover:bg-pink-900 text-white font-semibold px-5 py-2 rounded-lg text-sm whitespace-nowrap transition-colors"
            >
              پرداخت سفارش
            </Link>
          </div>
        )}

        {invoiceAvailable && (
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-pink-200 bg-pink-100 p-4 shadow-sm">
            <div>
              <p className="font-semibold text-gray-900">فاکتور فروش</p>
              <p className="mt-1 text-sm text-gray-600">فاکتور داخلی سفارش را مشاهده یا چاپ کنید.</p>
            </div>
            <Link
              href={`/account/orders/${order.order_number}/invoice`}
              className="rounded-lg bg-pink-800 px-5 py-2 text-sm font-semibold text-white hover:bg-pink-900"
            >
              مشاهده و چاپ فاکتور
            </Link>
          </div>
        )}

        {/* Items */}
        <section className="mb-6 overflow-hidden rounded-2xl border border-pink-300 bg-pink-100 shadow-sm">
          <div className="border-b border-pink-200 bg-pink-200/80 px-4 py-3">
            <h2 className="font-bold text-pink-950">اقلام سفارش</h2>
          </div>
          <div className="space-y-3 bg-pink-100/90 p-3 sm:p-4">
            {order.items.map((item) => (
              <article key={item.id} className="flex gap-3 rounded-xl border border-pink-200 bg-white p-3 shadow-md sm:p-4">
                <div className="h-16 w-16 flex-shrink-0 overflow-hidden rounded-lg bg-pink-100">
                  {item.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={item.image_url} alt={item.product_name} className="h-full w-full object-cover" />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-xs text-pink-300">—</div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <Link href={`/products/${item.product_slug}`} className="block text-sm font-semibold leading-6 text-gray-900 hover:text-pink-800 break-words sm:whitespace-nowrap">
                    {item.product_name}
                  </Link>
                  <p className="mt-1 text-xs text-pink-700">{item.brand_name}</p>
                  {item.variant_label && item.variant_label !== 'پیش‌فرض' && (
                    <p className="mt-1 text-xs text-gray-600">{item.variant_label}</p>
                  )}
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-pink-50 pt-2 text-sm">
                    <span className="text-gray-600">{item.quantity.toLocaleString('fa-IR')} × {item.price.toLocaleString('fa-IR')} تومان</span>
                    <span className="font-semibold text-gray-900">{item.subtotal.toLocaleString('fa-IR')} تومان</span>
                  </div>
                  {item.discount_amount > 0 && (
                    <div className="mt-2 flex justify-between text-xs text-green-700">
                      <span>تخفیف این قلم</span>
                      <span>−{item.discount_amount.toLocaleString('fa-IR')} تومان</span>
                    </div>
                  )}
                  {item.discount_amount > 0 && (
                    <div className="mt-2 flex justify-between rounded-lg bg-pink-50 px-3 py-2 text-sm font-bold text-pink-950">
                      <span>جمع پس از تخفیف</span>
                      <span>{item.final_subtotal.toLocaleString('fa-IR')} تومان</span>
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>

        <div className="grid md:grid-cols-2 gap-4">
          {/* Address */}
          <div className="rounded-2xl border border-rose-200 bg-rose-100/80 p-4 shadow-sm">
            <h2 className="mb-3 border-b border-rose-200 pb-2 font-bold text-pink-950">اطلاعات ارسال</h2>
            <div className="text-sm text-gray-700 space-y-1.5">
              <p>
                <span className="text-gray-500">گیرنده: </span>
                {order.first_name} {order.last_name}
              </p>
              <p>
                <span className="text-gray-500">موبایل: </span>
                <span dir="ltr">{order.mobile}</span>
              </p>
              <p>
                <span className="text-gray-500">استان/شهر: </span>
                {order.province_display} - {order.city}
              </p>
              <p>
                <span className="text-gray-500">آدرس: </span>
                {order.address}
              </p>
              {order.postal_code && (
                <p>
                  <span className="text-gray-500">کد پستی: </span>
                  <span dir="ltr">{order.postal_code}</span>
                </p>
              )}
              <p>
                <span className="text-gray-500">روش ارسال: </span>
                {order.shipping_method_name}
              </p>
            </div>
          </div>

          {/* Financial */}
          <div className="rounded-2xl border border-pink-300 bg-pink-100 p-4 shadow-sm">
            <h2 className="mb-3 border-b border-pink-200 pb-2 font-bold text-pink-950">خلاصه مالی</h2>
            <div className="text-sm space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-600">جمع کالاها</span>
                <span className="font-medium text-gray-900">
                  {order.subtotal.toLocaleString('fa-IR')} تومان
                </span>
              </div>
              {order.discount_amount > 0 && (
                <div className="flex justify-between text-green-700">
                  <span>تخفیف کل</span>
                  <span>−{order.discount_amount.toLocaleString('fa-IR')} تومان</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-gray-600">مالیات</span>
                <span className="font-medium text-gray-900">
                  {order.vat_amount.toLocaleString('fa-IR')} تومان
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">هزینه ارسال</span>
                <span
                  className={`font-medium ${
                    order.shipping_cost === 0
                      ? 'text-green-700'
                      : 'text-gray-900'
                  }`}
                >
                  {order.shipping_cost === 0
                    ? 'رایگان'
                    : `${order.shipping_cost.toLocaleString('fa-IR')} تومان`}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">هزینه بسته‌بندی</span>
                <span className="font-medium text-gray-900">
                  {order.packaging_cost === 0
                    ? 'رایگان'
                    : `${order.packaging_cost.toLocaleString('fa-IR')} تومان`}
                </span>
              </div>
              <div className="mt-2 flex justify-between rounded-xl border border-pink-200 bg-pink-200/70 px-3 py-3">
                <span className="font-bold text-pink-950">مبلغ نهایی</span>
                <span className="font-bold text-pink-900">
                  {order.total_amount.toLocaleString('fa-IR')} تومان
                </span>
              </div>
            </div>
          </div>
        </div>

        {['paid', 'processing', 'shipped', 'delivered'].includes(order.status) && (
          <section className="mt-6 rounded-2xl border border-rose-200 bg-rose-100/90 p-5 shadow-sm">
            <h2 className="mb-3 border-b border-rose-200 pb-3 font-bold text-pink-950">درخواست مرجوعی</h2>
            <p className="text-sm text-gray-600 mb-4">
              اقلام و تعداد موردنظر را مشخص کنید. درخواست پس از ثبت توسط پشتیبانی بررسی می‌شود.
            </p>
            {returnRequest ? (
              <div className="rounded-lg border border-pink-100 bg-pink-50 p-3 text-sm text-pink-950">
                درخواست مرجوعی شما ثبت شده است: {returnRequest.status_display}
              </div>
            ) : (
              <>
                <div className="space-y-3 mb-4">
                  {order.items.map((item) => (
                    <div key={item.id} className="flex items-center justify-between gap-3 rounded-lg border border-white/80 bg-white/90 px-3 py-2 text-sm shadow-sm">
                      <span className="text-gray-800">{item.product_name} (حداکثر {item.quantity.toLocaleString('fa-IR')})</span>
                      <input
                        type="text"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        value={returnQuantityInputs[item.id] ?? String(returnQuantities[item.id] || '')}
                        onChange={(event) => {
                          const rawValue = event.target.value;
                          setReturnQuantityInputs((current) => ({ ...current, [item.id]: rawValue }));
                          const normalizedValue = rawValue
                            .replace(/[۰-۹]/g, (digit) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit)))
                            .replace(/[٠-٩]/g, (digit) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit)));

                          if (normalizedValue === '') {
                            setInvalidReturnQuantities((current) => ({ ...current, [item.id]: false }));
                            setReturnQuantities((current) => ({ ...current, [item.id]: 0 }));
                            setReturnMessage(null);
                            return;
                          }
                          if (!/^[0-9]+$/.test(normalizedValue)) {
                            setInvalidReturnQuantities((current) => ({ ...current, [item.id]: true }));
                            setReturnMessage('تعداد مرجوعی باید فقط یک عدد صحیح باشد؛ بازه‌ای مثل ۲-۴ معتبر نیست.');
                            return;
                          }
                          const parsedValue = Number(normalizedValue);
                          if (!Number.isSafeInteger(parsedValue)) {
                            setInvalidReturnQuantities((current) => ({ ...current, [item.id]: true }));
                            setReturnMessage('تعداد مرجوعی معتبر نیست.');
                            return;
                          }
                          const value = Math.min(item.quantity, parsedValue);
                          setInvalidReturnQuantities((current) => ({ ...current, [item.id]: false }));
                          setReturnQuantityInputs((current) => ({ ...current, [item.id]: String(value) }));
                          setReturnQuantities((current) => ({ ...current, [item.id]: value }));
                          setReturnMessage(null);
                        }}
                        aria-label={`تعداد مرجوعی ${item.product_name}`}
                        aria-invalid={Boolean(invalidReturnQuantities[item.id])}
                        className="w-20 rounded-lg border border-pink-200 bg-white px-2 py-1 text-center focus:border-pink-500"
                      />
                    </div>
                  ))}
                </div>
                <label className="block text-sm font-medium text-gray-700 mb-2" htmlFor="return-reason">علت مرجوعی</label>
                <textarea
                  id="return-reason"
                  value={returnReason}
                  onChange={(event) => setReturnReason(event.target.value)}
                  rows={3}
                  className="w-full rounded-lg border border-gray-300 p-3 text-sm"
                  placeholder="علت درخواست را توضیح دهید..."
                />
                <button
                  type="button"
                  onClick={submitReturnRequest}
                  disabled={returnSubmitting}
                  className="mt-3 rounded-lg bg-pink-800 px-5 py-2 text-sm font-semibold text-white hover:bg-pink-900 disabled:opacity-50"
                >
                  {returnSubmitting ? 'در حال ثبت...' : 'ثبت درخواست مرجوعی'}
                </button>
              </>
            )}
            {returnMessage && <p className="mt-3 text-sm text-gray-700" role="status">{returnMessage}</p>}
          </section>
        )}

        {order.notes && (
          <div className="border border-gray-200 rounded-xl p-4 mt-4">
            <h2 className="font-bold text-gray-800 mb-2">یادداشت</h2>
            <p className="text-sm text-gray-700 whitespace-pre-line">
              {order.notes}
            </p>
          </div>
        )}

        <div className="mt-6 text-center">
          <Link
            href="/account"
            className="text-sm text-pink-800 hover:text-pink-900 font-medium"
          >
            ← بازگشت به سفارش‌های من
          </Link>
        </div>
      </div>
    </div>
  );
}
