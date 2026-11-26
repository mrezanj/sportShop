
'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import {
  fetchMyOrders,
  fetchProfile,
  updateProfile,
  type OrderDetail,
  type PaginatedResponse,
  type UserProfile,
} from '@/lib/api';

function formatOrderDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('fa-IR', {
    timeZone: 'Asia/Tehran',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-800 border-amber-200',
  paid: 'bg-blue-100 text-blue-800 border-blue-200',
  processing: 'bg-purple-800 text-purple-200',
  shipped: 'bg-indigo-800 text-indigo-800',
  delivered: 'bg-green-100 text-green-800 border-green-200',
  cancelled: 'bg-red-100 text-red-800 border-red-200',
};

export default function AccountPage() {
  const router = useRouter();
  const { isAuthenticated, loading: authLoading, token, user, logout } =
    useAuth();

  const [orders, setOrders] =
    useState<PaginatedResponse<OrderDetail> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [birthDate, setBirthDate] = useState('');
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSuccess, setProfileSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login?returnTo=/account');
    }
  }, [authLoading, isAuthenticated, router]);

  const handleProfileSave = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!token) return;

    setProfileSaving(true);
    setProfileError(null);
    setProfileSuccess(null);

    try {
      const updatedProfile = await updateProfile(birthDate, token);
      setProfile(updatedProfile);
      setBirthDate(updatedProfile.birth_date ?? '');
      setProfileSuccess('اطلاعات پروفایل با موفقیت ذخیره شد.');
    } catch (err) {
      setProfileError(
        err instanceof Error
          ? err.message
          : 'خطا در ذخیره اطلاعات پروفایل.'
      );
    } finally {
      setProfileSaving(false);
    }
  };

  useEffect(() => {
    if (!token) return;

    fetchMyOrders(token)
      .then(setOrders)
      .catch(() => setError('خطا در دریافت سفارش‌ها.'))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!token) return;

    fetchProfile(token)
      .then((data) => {
        setProfile(data);
        setBirthDate(data.birth_date ?? '');
      })
      .catch(() => {
        setProfileError('خطا در دریافت اطلاعات پروفایل.');
      })
      .finally(() => setProfileLoading(false));
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
        <div className="rounded-2xl border border-rose-200 bg-rose-50/80 p-6 mb-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-sm">
          <div>
            <p className="text-xs text-gray-600 mb-1">حساب کاربری</p>
            <p className="text-lg font-bold text-pink-900">
              {profile?.mobile ?? user?.mobile}
            </p>
          </div>

          <button
            onClick={logout}
            className="text-sm text-red-600 hover:text-red-800 border border-red-200 rounded-lg px-4 py-2 bg-white"
          >
            خروج از حساب
          </button>
        </div>

        {/* Profile form */}
        <div className="rounded-2xl border border-rose-200 bg-white p-6 mb-8 shadow-sm">
          <h2 className="text-lg font-bold text-pink-900 mb-2">
            اطلاعات پروفایل
          </h2>

          <p className="text-sm text-gray-600 mb-5">
            برای خرید محصولاتی که محدودیت سنی دارند، ثبت تاریخ تولد الزامی است.
          </p>

          {profileError && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3 mb-4">
              {profileError}
            </div>
          )}

          {profileSuccess && (
            <div className="bg-green-50 border border-green-200 text-green-700 text-sm rounded-lg p-3 mb-4">
              {profileSuccess}
            </div>
          )}

          <form onSubmit={handleProfileSave}>
            <div className="mb-4">
              <label
                htmlFor="profile-mobile"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                شماره موبایل
              </label>

              <input
                id="profile-mobile"
                type="text"
                value={profile?.mobile ?? user?.mobile ?? ''}
                readOnly
                dir="ltr"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 bg-gray-100 text-gray-600"
              />
            </div>

            <div className="mb-5">
              <label
                htmlFor="birth-date"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                تاریخ تولد
              </label>

              <input
                id="birth-date"
                type="date"
                value={birthDate}
                onChange={(event) => {
                  setBirthDate(event.target.value);
                  setProfileError(null);
                  setProfileSuccess(null);
                }}
                disabled={profileLoading || profileSaving}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-800 disabled:bg-gray-100"
              />

              <p className="text-xs text-gray-500 mt-2">
                تاریخ تولد را به میلادی وارد کنید. در صورت نداشتن محدودیت سنی
                برای محصولات، ثبت آن الزامی نیست.
              </p>
            </div>

            <button
              type="submit"
              disabled={profileLoading || profileSaving}
              className="bg-pink-800 hover:bg-pink-900 disabled:bg-gray-400 text-white rounded-lg px-6 py-2 text-sm font-medium"
            >
              {profileSaving ? 'در حال ذخیره...' : 'ذخیره اطلاعات'}
            </button>
          </form>
        </div>

        {/* Orders */}
        <section className="rounded-2xl border border-rose-200 bg-rose-50/70 p-4 shadow-sm sm:p-6">
          <h1 className="text-xl font-bold text-pink-900 mb-4">
            سفارش‌های من
          </h1>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3 mb-4">
              {error}
            </div>
          )}

          {!orders || orders.results.length === 0 ? (
            <div className="text-center py-16 rounded-xl border border-dashed border-rose-200 bg-white">
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
                  className="block rounded-xl border border-rose-200 bg-white p-4 shadow-sm hover:border-pink-400 hover:shadow-md transition-all"
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
                        {formatOrderDate(order.created_at)}
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
        </section>
      </div>
    </div>
  );
}
