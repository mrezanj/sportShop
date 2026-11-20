'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useCart } from '@/context/CartContext';
import { useAuth } from '@/context/AuthContext';
import {
  fetchProvinces,
  fetchShippingMethods,
  createOrder,
  type Province,
  type ShippingMethod,
} from '@/lib/api';

const VAT_RATE = 0.10;

export default function CheckoutPage() {
  const router = useRouter();
  const { isAuthenticated, loading: authLoading, user, token } = useAuth();
  const { items, totalPrice, clearCart } = useCart();

  const [provinces, setProvinces] = useState<Province[]>([]);
  const [shippingMethods, setShippingMethods] = useState<ShippingMethod[]>([]);
  const [loadingMethods, setLoadingMethods] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    mobile: user?.mobile ?? '',
    province: '',
    city: '',
    address: '',
    postal_code: '',
    notes: '',
  });
  const [selectedMethodSlug, setSelectedMethodSlug] = useState('');

  // Redirect if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login?returnTo=/checkout');
    }
  }, [authLoading, isAuthenticated, router]);

  // Load provinces
  useEffect(() => {
    fetchProvinces().then(setProvinces);
  }, []);

  // Pre-fill mobile
  useEffect(() => {
    if (user?.mobile && !form.mobile) {
      setForm((f) => ({ ...f, mobile: user.mobile! }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  // Load shipping methods when province changes
  useEffect(() => {
    if (!form.province) {
      setShippingMethods([]);
      setSelectedMethodSlug('');
      return;
    }
    setLoadingMethods(true);
    fetchShippingMethods(form.province)
      .then((methods) => {
        setShippingMethods(methods);
        setSelectedMethodSlug(methods[0]?.slug ?? '');
      })
      .finally(() => setLoadingMethods(false));
  }, [form.province]);

  // Redirect if cart empty (only after mount)
  useEffect(() => {
    if (!authLoading && items.length === 0 && !submitting) {
      router.push('/cart');
    }
  }, [items.length, authLoading, router, submitting]);

  const selectedMethod = shippingMethods.find(
    (m) => m.slug === selectedMethodSlug
  );
  const shippingCost = selectedMethod?.cost ?? 0;
  const vat = Math.round(totalPrice * VAT_RATE);
  const grandTotal = totalPrice + vat + shippingCost;

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setForm((f) => ({ ...f, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!form.province) return setError('استان را انتخاب کنید.');
    if (!form.city.trim()) return setError('شهر را وارد کنید.');
    if (!form.address.trim() || form.address.trim().length < 10)
      return setError('آدرس را کامل وارد کنید (حداقل ۱۰ کاراکتر).');
    if (!selectedMethodSlug) return setError('روش ارسال را انتخاب کنید.');
    if (!/^09\d{9}$/.test(form.mobile))
      return setError('شماره موبایل معتبر نیست.');
    if (!token) return setError('ابتدا وارد حساب کاربری شوید.');

    setSubmitting(true);
    try {
      const response = await createOrder(
        {
          items: items.map((i) => ({
            variant_id: i.variantId,
            quantity: i.quantity,
          })),
          shipping_method_slug: selectedMethodSlug,
          province: form.province,
          city: form.city,
          address: form.address,
          postal_code: form.postal_code,
          first_name: form.first_name,
          last_name: form.last_name,
          mobile: form.mobile,
          notes: form.notes,
        },
        token
      );

      // Don't clear cart yet - payment must succeed first
      router.push(`/checkout/payment?order=${response.order_number}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'خطای نامشخص');
      setSubmitting(false);
    }
  };

  if (authLoading || items.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500">
        در حال بارگذاری...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-page" dir="rtl">
      <div className="container mx-auto px-4 py-8">
        <nav className="text-sm text-gray-500 mb-6">
          <Link href="/cart" className="hover:text-pink-800">
            سبد خرید
          </Link>
          <span className="mx-2">/</span>
          <span className="text-gray-800">اطلاعات ارسال و پرداخت</span>
        </nav>

        <h1 className="text-2xl font-bold text-pink-900 mb-6">
          تکمیل اطلاعات خرید
        </h1>

        <form onSubmit={handleSubmit} className="grid lg:grid-cols-3 gap-6">
          {/* Form fields */}
          <div className="lg:col-span-2 space-y-4">
            <div className="border border-gray-200 rounded-xl p-4 bg-white">
              <h2 className="font-bold text-gray-800 mb-3">اطلاعات گیرنده</h2>
              <div className="grid sm:grid-cols-2 gap-3">
                <input
                  name="first_name"
                  value={form.first_name}
                  onChange={handleChange}
                  placeholder="نام *"
                  required
                  className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pink-800 text-gray-900"
                />
                <input
                  name="last_name"
                  value={form.last_name}
                  onChange={handleChange}
                  placeholder="نام خانوادگی *"
                  required
                  className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pink-800 text-gray-900"
                />
                <input
                  name="mobile"
                  value={form.mobile}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      mobile: e.target.value.replace(/[^\d]/g, '').slice(0, 11),
                    }))
                  }
                  placeholder="شماره موبایل *"
                  dir="ltr"
                  className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pink-800 text-center text-gray-900"
                  required
                />
                <input
                  name="postal_code"
                  value={form.postal_code}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      postal_code: e.target.value
                        .replace(/[^\d]/g, '')
                        .slice(0, 10),
                    }))
                  }
                  placeholder="کد پستی (اختیاری)"
                  dir="ltr"
                  className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pink-800 text-center text-gray-900"
                />
              </div>
            </div>

            <div className="border border-gray-200 rounded-xl p-4 bg-white">
              <h2 className="font-bold text-gray-800 mb-3">آدرس</h2>
              <div className="grid sm:grid-cols-2 gap-3 mb-3">
                <select
                  name="province"
                  value={form.province}
                  onChange={handleChange}
                  required
                  className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pink-800 text-gray-900 bg-white"
                >
                  <option value="">انتخاب استان *</option>
                  {provinces.map((p) => (
                    <option key={p.slug} value={p.slug}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <input
                  name="city"
                  value={form.city}
                  onChange={handleChange}
                  placeholder="شهر *"
                  required
                  className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pink-800 text-gray-900"
                />
              </div>
              <textarea
                name="address"
                value={form.address}
                onChange={handleChange}
                placeholder="آدرس کامل پستی *"
                required
                rows={3}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pink-800 text-gray-900"
              />
            </div>

            <div className="border border-gray-200 rounded-xl p-4 bg-white">
              <h2 className="font-bold text-gray-800 mb-3">روش ارسال</h2>
              {!form.province ? (
                <p className="text-sm text-gray-500">
                  ابتدا استان را انتخاب کنید.
                </p>
              ) : loadingMethods ? (
                <p className="text-sm text-gray-500">در حال بارگذاری...</p>
              ) : shippingMethods.length === 0 ? (
                <p className="text-sm text-red-600">
                  برای این استان روش ارسالی تعریف نشده است.
                </p>
              ) : (
                <div className="space-y-2">
                  {shippingMethods.map((m) => (
                    <label
                      key={m.id}
                      className={`flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${selectedMethodSlug === m.slug
                          ? 'border-pink-800 bg-pink-50'
                          : 'border-gray-200 hover:border-pink-300'
                        }`}
                    >
                      <input
                        type="radio"
                        name="shipping_method"
                        value={m.slug}
                        checked={selectedMethodSlug === m.slug}
                        onChange={() => setSelectedMethodSlug(m.slug)}
                        className="mt-1 accent-pink-800"
                      />
                      <div className="flex-1">
                        <div className="flex justify-between items-center">
                          <span className="font-medium text-gray-900">
                            {m.name}
                          </span>
                          <span className="text-sm font-bold text-pink-900">
                            {m.cost === 0
                              ? 'رایگان'
                              : `${(m.cost ?? 0).toLocaleString('fa-IR')} تومان`}
                          </span>
                        </div>
                        {m.description && (
                          <p className="text-xs text-gray-600 mt-1">
                            {m.description}
                          </p>
                        )}
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>

            <div className="border border-gray-200 rounded-xl p-4 bg-white">
              <h2 className="font-bold text-gray-800 mb-3">
                یادداشت سفارش (اختیاری)
              </h2>
              <textarea
                name="notes"
                value={form.notes}
                onChange={handleChange}
                rows={2}
                placeholder="اگر نکته‌ای برای ارسال دارید بنویسید."
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pink-800 text-gray-900"
              />
            </div>
          </div>

          {/* Summary */}
          <aside className="bg-pink-50 rounded-xl p-6 h-fit sticky top-24">
            <h2 className="font-bold text-pink-900 mb-4">خلاصه سفارش</h2>

            <div className="space-y-2 mb-4 max-h-64 overflow-y-auto">
              {items.map((i) => (
                <div
                  key={i.variantId}
                  className="flex justify-between text-xs text-gray-700"
                >
                  <span className="truncate ml-2">
                    {i.productName} × {i.quantity}
                  </span>
                  <span className="whitespace-nowrap font-medium">
                    {(i.price * i.quantity).toLocaleString('fa-IR')}
                  </span>
                </div>
              ))}
            </div>

            <div className="space-y-2 text-sm border-t border-pink-300 pt-3">
              <div className="flex justify-between">
                <span className="text-gray-700">جمع کالاها</span>
                <span className="font-semibold text-gray-900">
                  {totalPrice.toLocaleString('fa-IR')}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-700">مالیات (۱۰٪)</span>
                <span className="font-semibold text-gray-900">
                  {vat.toLocaleString('fa-IR')}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-700">هزینه ارسال</span>
                <span
                  className={`font-semibold ${shippingCost === 0 ? 'text-green-700' : 'text-gray-900'
                    }`}
                >
                  {!selectedMethod
                    ? '—'
                    : shippingCost === 0
                      ? 'رایگان'
                      : shippingCost.toLocaleString('fa-IR')}
                </span>
              </div>
              <div className="border-t border-pink-300 pt-3 flex justify-between">
                <span className="font-bold text-gray-900">مبلغ نهایی</span>
                <span className="font-bold text-pink-900 text-lg">
                  {grandTotal.toLocaleString('fa-IR')} تومان
                </span>
              </div>
            </div>

            {error && (
              <div className="mt-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || !selectedMethodSlug}
              className="w-full mt-4 bg-pink-800 hover:bg-pink-900 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition-colors"
            >
              {submitting ? 'در حال ثبت سفارش...' : 'ثبت سفارش'}
            </button>

            <p className="text-xs text-gray-600 text-center mt-3">
              با ثبت سفارش، قوانین و شرایط فروشگاه را می‌پذیرید.
            </p>
          </aside>
        </form>
      </div>
    </div>
  );
}