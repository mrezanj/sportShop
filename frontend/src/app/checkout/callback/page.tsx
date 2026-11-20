'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { useCart } from '@/context/CartContext';
import { verifyPayment } from '@/lib/api';

function CallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const orderNumber = searchParams.get('order') || '';
  const status = searchParams.get('status') || '';
  const authority = searchParams.get('authority') || '';

  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const { clearCart } = useCart();

  const [message, setMessage] = useState('در حال بررسی پرداخت...');
  const [error, setError] = useState<string | null>(null);
  const hasRun = useRef(false);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login?returnTo=/account');
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    // Prevent duplicate verify (React StrictMode double-runs effects in dev)
    if (hasRun.current) return;
    if (!token || !orderNumber) return;
    hasRun.current = true;

    verifyPayment(orderNumber, status, authority, token)
      .then((res) => {
        if (res.success) {
          clearCart();
          setMessage('پرداخت با موفقیت انجام شد. در حال انتقال...');
          router.replace(
            `/checkout/success?order=${orderNumber}${
              res.ref_id ? `&ref=${res.ref_id}` : ''
            }`
          );
        } else {
          setError(res.message || 'پرداخت ناموفق بود.');
          router.replace(`/checkout/failed?order=${orderNumber}`);
        }
      })
      .catch(() => {
        setError('خطا در بررسی پرداخت.');
        router.replace(`/checkout/failed?order=${orderNumber}`);
      });
  }, [token, orderNumber, status, authority, clearCart, router]);

  return (
    <div className="min-h-screen flex items-center justify-center px-4" dir="rtl">
      <div className="text-center max-w-md">
        <div className="text-5xl mb-4 animate-pulse">⏳</div>
        <p className="text-gray-700 mb-2">{message}</p>
        {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
        <p className="text-xs text-gray-500 mt-4">
          لطفاً صفحه را نبندید...
        </p>
      </div>
    </div>
  );
}

export default function CallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-gray-500">
          در حال بارگذاری...
        </div>
      }
    >
      <CallbackContent />
    </Suspense>
  );
}