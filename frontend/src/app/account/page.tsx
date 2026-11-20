'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import {
  fetchMyOrders,
  type OrderDetail,
  type PaginatedResponse,
} from '@/lib/api';

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-800 border-amber-200',
  paid: 'bg-blue-100 text-blue-800 border-blue-200',
  processing: 'bg-purple-100 text-purple-800 border-purple-200',
  shipped: 'bg-indigo-100 text-indigo-800 border-indigo-200',
  delivered: 'bg-green-100 text-green-800 border-green-200',
  cancelled: 'bg-red-100 text-red-800 border-red-200',
};

export default function AccountPage() {
  const router = useRouter();
  const { isAuthenticated, loading: authLoading, token, user, logout } = useAuth();

  const [orders, setOrders] =
    useState<PaginatedResponse<OrderDetail> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login?returnTo=/account');
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    fetchMyOrders(token)
      .then(setOrders)
      .catch(() => setError('خطا در دریافت سفارش‌ها.'))
      .finally(() => setLoading(false));
  }, [token]);

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500">
        در حال بارگذاری...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-page" dir="rtl">
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        {/* Profile header */}
        <div className="bg-pink-50 rounded-xl p-6 mb-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <p className="text-xs text-gray-600 mb-1">حساب کاربری</p>
            <p className="text-lg font-bold text-pink-900">
              {user?.mobile}
            </p>
          </div>
          <button
            onClick={logout}
            className="text-sm text-red-600 hover:text-red-800 border border-red-200 rounded-lg px-4 py-2 bg-white"
          >
            خروج از حساب
          </button>
        </div>

        {/* Orders */}
        <div>
          <h1 className="text-xl font-bold text-pink-900 mb-4">
            سفارش‌های من
          </h1>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3 mb-4">
              {error}
            </div>
          )}

          {!orders || orders.results.length === 0 ? (
            <div className="text-center py-16 bg-gray-50 rounded-xl">
              <div className="text-5xl mb-3">📦</div>
              <p className="text-gray-700 mb-4">
                هنوز سفارشی ثبت نکرده‌اید.
              </p>
              <Link
                href="/products"
                className="inline-block bg-pink-800 hover:bg-pink-900 text-white px-6 py-2 rounded-lg text-sm"
              >
                مشاهده محصولات
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {orders.results.map((order) => (
                <Link
                  key={order.id}
                  href={`/account/orders/${order.order_number}`}
                  className="block border border-gray-200 rounded-xl p-4 hover:border-pink-300 hover:shadow-sm transition-all bg-white"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                    <div>
                      <p className="text-xs text-gray-500">شماره سفارش</p>
                      <p
                        className="font-bold text-gray-900 text-sm"
                        dir="ltr"
                      >
                        {order.order_number}
                      </p>
                    </div>
                    <span
                      className={`text-xs px-3 py-1 rounded-full border ${
                        STATUS_COLORS[order.status] ??
                        'bg-gray-100 text-gray-800 border-gray-200'
                      }`}
                    >
                      {order.status_display}
                    </span>
                  </div>

                  <div className="flex flex-wrap justify-between gap-3 text-sm">
                    <div className="text-gray-600">
                      <span>{order.items.length} کالا</span>
                      <span className="mx-2">·</span>
                      <span>
                        {new Date(order.created_at).toLocaleDateString('fa-IR')}
                      </span>
                    </div>
                    <div className="font-bold text-pink-900">
                      {order.total_amount.toLocaleString('fa-IR')} تومان
                    </div>
                  </div>

                  {order.tracking_code && (
                    <div className="mt-2 text-xs text-indigo-700 bg-indigo-50 rounded-lg px-3 py-2">
                      کد رهگیری: <span dir="ltr">{order.tracking_code}</span>
                    </div>
                  )}
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}