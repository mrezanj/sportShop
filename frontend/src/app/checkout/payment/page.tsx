
'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import {
  initiatePayment,
  fetchOrderDetail,
  type OrderDetail,
} from '@/lib/api';

type OrderRequestResult = {
  key: string;
  order: OrderDetail | null;
  error: string | null;
};

function PaymentContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const orderNumber = searchParams.get('order') || '';
  const { isAuthenticated, loading: authLoading, token } = useAuth();

  const [requestResult, setRequestResult] =
    useState<OrderRequestResult | null>(null);
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [redirecting, setRedirecting] = useState(false);

  const requestKey = token && orderNumber
    ? JSON.stringify([orderNumber, token])
    : '';

  const currentResult =
    requestResult?.key === requestKey ? requestResult : null;

  const order = currentResult?.order ?? null;
  const error = paymentError ?? currentResult?.error ?? null;
  const loading = Boolean(token && orderNumber && !currentResult);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push(
        `/login?returnTo=/checkout/payment?order=${orderNumber}`
      );
    }
  }, [authLoading, isAuthenticated, router, orderNumber]);

  useEffect(() => {
    if (!token || !orderNumber) return;

    let cancelled = false;

    fetchOrderDetail(orderNumber, token)
      .then((data) => {
        if (cancelled) return;

        setRequestResult({
          key: requestKey,
          order: data,
          error: null,
        });

        if (data.status === 'paid') {
          router.push(`/account/orders/${orderNumber}`);
        }
      })
      .catch(() => {
        if (cancelled) return;

        setRequestResult({
          key: requestKey,
          order: null,
          error: 'سفارش یافت نشد.',
        });
      });

    return () => {
      cancelled = true;
    };
  }, [token, orderNumber, requestKey, router]);

  const handlePay = async () => {
    if (!token || !order) return;

    setPaymentError(null);
    setRedirecting(true);

    try {
      const res = await initiatePayment(order.order_number, token);
      window.location.href = res.redirect_url;
    } catch (err) {
      setPaymentError(
        err instanceof Error ? err.message : 'خطای نامشخص'
      );
      setRedirecting(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500">
        در حال بارگذاری...
      </div>
    );
  }

  if (error && !order) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4" dir="rtl">
        <div className="text-center">
          <p className="text-gray-700 mb-4">{error}</p>
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

  if (!order) return null;

  return (
    <div className="min-h-screen bg-page" dir="rtl">
      <div className="container mx-auto px-4 py-8 max-w-2xl">
        <nav className="text-sm text-gray-500 mb-6">
          <Link href="/cart" className="hover:text-pink-800">
            سبد خرید
          </Link>
          <span className="mx-2">/</span>
          <span className="text-gray-800">پرداخت</span>
        </nav>

        <div className="bg-pink-50 border border-pink-200 rounded-xl p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-xs text-gray-600 mb-1">شماره سفارش</p>
              <p className="font-bold text-gray-900" dir="ltr">
                {order.order_number}
              </p>
            </div>
            <span className="text-xs px-3 py-1 rounded-full bg-amber-100 text-amber-800 border border-amber-200">
              در انتظار پرداخت
            </span>
          </div>

          <div className="border-t border-pink-200 pt-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-700">جمع کالاها</span>
              <span className="font-medium text-gray-900">
                {order.subtotal.toLocaleString('fa-IR')} تومان
              </span>
            </div>

            <div className="flex justify-between">
              <span className="text-gray-700">مالیات</span>
              <span className="font-medium text-gray-900">
                {order.vat_amount.toLocaleString('fa-IR')} تومان
              </span>
            </div>

            <div className="flex justify-between">
              <span className="text-gray-700">هزینه ارسال</span>
              <span
                className={`font-medium ${
                  order.shipping_is_free || order.shipping_cost === 0
                    ? 'text-green-700'
                    : 'text-gray-900'
                }`}
              >
                {order.shipping_is_free || order.shipping_cost === 0
                  ? 'رایگان'
                  : `${order.shipping_cost.toLocaleString('fa-IR')} تومان`}
              </span>
            </div>

            <div className="flex justify-between">
              <span className="text-gray-700">هزینه بسته‌بندی</span>
              <span
                className={`font-medium ${
                  order.packaging_is_free || order.packaging_cost === 0
                    ? 'text-green-700'
                    : 'text-gray-900'
                }`}
              >
                {order.packaging_is_free || order.packaging_cost === 0
                  ? 'رایگان'
                  : `${order.packaging_cost.toLocaleString('fa-IR')} تومان`}
              </span>
            </div>

            <div className="border-t border-pink-300 pt-3 flex justify-between items-center">
              <span className="font-bold text-gray-900">مبلغ قابل پرداخت</span>
              <span className="font-bold text-pink-900 text-xl">
                {order.total_amount.toLocaleString('fa-IR')} تومان
              </span>
            </div>
          </div>
        </div>

        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6 text-sm text-blue-800">
          ℹ️ با کلیک روی دکمه زیر، به درگاه پرداخت منتقل می‌شوید. لطفاً
          اطلاعات پرداخت را کامل کنید.
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3 mb-4">
            {error}
          </div>
        )}

        <button
          onClick={handlePay}
          disabled={redirecting}
          className="w-full bg-pink-800 hover:bg-pink-900 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition-colors"
        >
          {redirecting ? 'در حال انتقال به درگاه...' : 'پرداخت آنلاین'}
        </button>

        <Link
          href="/cart"
          className="block text-center text-sm text-pink-800 hover:text-pink-900 mt-4 font-medium"
        >
          بازگشت به سبد خرید
        </Link>
      </div>
    </div>
  );
}

export default function PaymentPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-gray-500">
          در حال بارگذاری...
        </div>
      }
    >
      <PaymentContent />
    </Suspense>
  );
}
