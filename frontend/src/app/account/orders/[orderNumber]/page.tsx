
'use client';

import { Suspense, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import { fetchOrderDetail, type OrderDetail } from '@/lib/api';

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-800 border-amber-200',
  paid: 'bg-blue-100 text-blue-800 border-blue-200',
  processing: 'bg-purple-100 text-purple-800 border-purple-200',
  shipped: 'bg-indigo-100 text-indigo-800 border-indigo-200',
  delivered: 'bg-green-100 text-green-800 border-green-200',
  cancelled: 'bg-red-100 text-red-800 border-red-200',
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push(`/login?returnTo=/account/orders/${orderNumber}`);
    }
  }, [authLoading, isAuthenticated, router, orderNumber]);

  useEffect(() => {
    if (!token || !orderNumber) return;

    fetchOrderDetail(orderNumber, token)
      .then(setOrder)
      .catch(() => setError('سفارش یافت نشد.'))
      .finally(() => setLoading(false));
  }, [token, orderNumber]);

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
      <div className="container mx-auto px-4 py-8 max-w-4xl">
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
        <div className="bg-pink-50 rounded-xl p-5 mb-6">
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
            {new Date(order.created_at).toLocaleDateString('fa-IR', {
              year: 'numeric',
              month: 'long',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
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

        {/* Items */}
        <div className="border border-gray-200 rounded-xl overflow-hidden mb-6">
          <div className="bg-gray-50 px-4 py-3 border-b border-gray-200">
            <h2 className="font-bold text-gray-800">اقلام سفارش</h2>
          </div>
          <div className="divide-y divide-gray-100">
            {order.items.map((item, idx) => (
              <div key={idx} className="p-4 flex gap-3">
                <div className="w-16 h-16 bg-pink-50 rounded-lg overflow-hidden flex-shrink-0">
                  {item.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={item.image_url}
                      alt={item.product_name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-pink-300 text-xs">
                      —
                    </div>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <Link
                    href={`/products/${item.product_slug}`}
                    className="font-medium text-gray-900 hover:text-pink-800 text-sm line-clamp-2"
                  >
                    {item.product_name}
                  </Link>
                  <p className="text-xs text-pink-600 mt-1">
                    {item.brand_name}
                  </p>
                  {item.variant_label && item.variant_label !== 'پیش‌فرض' && (
                    <p className="text-xs text-gray-600 mt-1">
                      {item.variant_label}
                    </p>
                  )}
                  <div className="flex justify-between items-center mt-2 text-sm">
                    <span className="text-gray-600">
                      {item.quantity.toLocaleString('fa-IR')} ×{' '}
                      {item.price.toLocaleString('fa-IR')} تومان
                    </span>
                    <span className="font-medium text-gray-900">
                      {item.subtotal.toLocaleString('fa-IR')} تومان
                    </span>
                  </div>
                  {item.discount_amount > 0 && (
                    <div className="mt-1 flex justify-between text-xs text-green-700">
                      <span>تخفیف این قلم</span>
                      <span>−{item.discount_amount.toLocaleString('fa-IR')} تومان</span>
                    </div>
                  )}
                  {item.discount_amount > 0 && (
                    <div className="mt-1 flex justify-between text-sm font-bold text-pink-900">
                      <span>جمع پس از تخفیف</span>
                      <span>{item.final_subtotal.toLocaleString('fa-IR')} تومان</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          {/* Address */}
          <div className="border border-gray-200 rounded-xl p-4">
            <h2 className="font-bold text-gray-800 mb-3">اطلاعات ارسال</h2>
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
          <div className="border border-gray-200 rounded-xl p-4">
            <h2 className="font-bold text-gray-800 mb-3">خلاصه مالی</h2>
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
              <div className="border-t pt-2 flex justify-between">
                <span className="font-bold text-gray-900">مبلغ نهایی</span>
                <span className="font-bold text-pink-900">
                  {order.total_amount.toLocaleString('fa-IR')} تومان
                </span>
              </div>
            </div>
          </div>
        </div>

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
