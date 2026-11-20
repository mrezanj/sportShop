'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';

function FailedContent() {
  const searchParams = useSearchParams();
  const orderNumber = searchParams.get('order') || '';

  return (
    <div className="min-h-screen bg-white flex items-center justify-center px-4 py-12" dir="rtl">
      <div className="w-full max-w-lg text-center">
        <div className="text-7xl mb-6">❌</div>
        <h1 className="text-2xl font-bold text-red-700 mb-3">
          پرداخت انجام نشد
        </h1>
        <p className="text-gray-600 mb-6">
          پرداخت شما لغو شد یا ناموفق بود. سفارش شما همچنان در وضعیت
          «در انتظار پرداخت» باقی مانده است. می‌توانید دوباره تلاش کنید.
        </p>

        {orderNumber && (
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 mb-6">
            <p className="text-sm text-gray-700 mb-1">شماره سفارش</p>
            <p className="text-lg font-bold text-gray-900" dir="ltr">
              {orderNumber}
            </p>
          </div>
        )}

        <div className="space-y-3">
          {orderNumber && (
            <Link
              href={`/checkout/payment?order=${orderNumber}`}
              className="block bg-pink-800 hover:bg-pink-900 text-white font-semibold py-3 rounded-lg transition-colors"
            >
              تلاش مجدد برای پرداخت
            </Link>
          )}
          <Link
            href="/account"
            className="block text-sm text-pink-800 hover:text-pink-900 font-medium"
          >
            مشاهده سفارش‌های من
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function FailedPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-gray-500">
          در حال بارگذاری...
        </div>
      }
    >
      <FailedContent />
    </Suspense>
  );
}