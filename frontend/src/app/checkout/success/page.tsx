'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';

function SuccessContent() {
  const searchParams = useSearchParams();
  const orderNumber = searchParams.get('order') || '';

  return (
    <div className="min-h-screen bg-white flex items-center justify-center px-4 py-12" dir="rtl">
      <div className="w-full max-w-lg text-center">
        <div className="text-7xl mb-6">🎉</div>
        <h1 className="text-2xl font-bold text-pink-900 mb-3">
          سفارش شما با موفقیت ثبت شد
        </h1>
        <p className="text-gray-600 mb-6">
          همکاران ما به‌زودی برای هماهنگی ارسال با شما تماس می‌گیرند.
        </p>

        {orderNumber && (
          <div className="bg-pink-50 border border-pink-200 rounded-xl p-4 mb-6">
            <p className="text-sm text-gray-700 mb-1">شماره سفارش</p>
            <p className="text-xl font-bold text-pink-900" dir="ltr">
              {orderNumber}
            </p>
            <p className="text-xs text-gray-500 mt-2">
              این شماره را برای پیگیری نگه دارید.
            </p>
          </div>
        )}

        <div className="space-y-3">
          <Link
            href="/products"
            className="block bg-pink-800 hover:bg-pink-900 text-white font-semibold py-3 rounded-lg transition-colors"
          >
            ادامه خرید
          </Link>
          <Link
            href="/"
            className="block text-sm text-pink-800 hover:text-pink-900 font-medium"
          >
            بازگشت به صفحه اصلی
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function SuccessPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-gray-500">
          در حال بارگذاری...
        </div>
      }
    >
      <SuccessContent />
    </Suspense>
  );
}