
'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useCart } from '@/context/CartContext';
import { useAuth } from '@/context/AuthContext';
import {
  fetchProvinces,
  fetchCities,
  fetchShippingMethods,
  createOrder,
  type Province,
  type City,
  type ShippingMethod,
} from '@/lib/api';
import {
  fetchShippingPreview,
  type ShippingPreviewResponse,
} from '@/lib/shipping';

export default function CheckoutPage() {
  const router = useRouter();
  const { isAuthenticated, loading: authLoading, user, token } = useAuth();
  const { items, totalPrice } = useCart();

  const [provinces, setProvinces] = useState<Province[]>([]);
  const [cities, setCities] = useState<City[]>([]);
  const [shippingMethods, setShippingMethods] = useState<ShippingMethod[]>([]);
  const [loadingCities, setLoadingCities] = useState(false);
  const [loadingMethods, setLoadingMethods] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [preview, setPreview] = useState<ShippingPreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [priceConfirmed, setPriceConfirmed] = useState(false);
  const [quoteRefreshKey, setQuoteRefreshKey] = useState(0);
  const [discountCodeInput, setDiscountCodeInput] = useState('');
  const [discountCode, setDiscountCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    mobile: user?.mobile ?? '',
    province: '',
    city_code: '',
    address: '',
    postal_code: '',
    notes: '',
  });

  const [selectedMethodSlug, setSelectedMethodSlug] = useState('');

  // Redirect if not authenticated.
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login?returnTo=/checkout');
    }
  }, [authLoading, isAuthenticated, router]);

  // Load provinces.
  useEffect(() => {
    fetchProvinces().then(setProvinces);
  }, []);

  // Pre-fill mobile.
  useEffect(() => {
    if (user?.mobile && !form.mobile) {
      setForm((f) => ({ ...f, mobile: user.mobile! }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  // Load cities whenever the province changes.
  useEffect(() => {
    let cancelled = false;

    setCities([]);
    setShippingMethods([]);
    setSelectedMethodSlug('');
    setPreview(null);
    setPreviewError(null);
    setPriceConfirmed(false);

    if (!form.province) {
      setLoadingCities(false);
      setLoadingMethods(false);
      return;
    }

    setLoadingCities(true);

    fetchCities(form.province)
      .then((result) => {
        if (!cancelled) {
          setCities(result);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingCities(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [form.province]);

  // Load shipping methods whenever both province and city are selected.
  useEffect(() => {
    let cancelled = false;

    setShippingMethods([]);
    setSelectedMethodSlug('');
    setPreview(null);
    setPreviewError(null);

    if (!form.province || !form.city_code) {
      setLoadingMethods(false);
      return;
    }

    setLoadingMethods(true);

    fetchShippingMethods(form.province, form.city_code)
      .then((methods) => {
        if (!cancelled) {
          setShippingMethods(methods);
          setSelectedMethodSlug(methods[0]?.slug ?? '');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingMethods(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [form.province, form.city_code]);

  // Redirect if cart is empty.
  useEffect(() => {
    if (!authLoading && items.length === 0 && !submitting) {
      router.push('/cart');
    }
  }, [items.length, authLoading, router, submitting]);

  // Calculate the actual order amounts whenever cart or shipping selection changes.
  useEffect(() => {
    let cancelled = false;

    setPreview(null);
    setPreviewError(null);
    setPriceConfirmed(false);
    setError(null);

    if (
      !token ||
      !form.province ||
      !form.city_code ||
      !selectedMethodSlug ||
      items.length === 0
    ) {
      setLoadingPreview(false);
      return;
    }

    setLoadingPreview(true);

    fetchShippingPreview(
      {
        items: items.map((item) => ({
          variant_id: item.variantId,
          quantity: item.quantity,
        })),
        shipping_method_slug: selectedMethodSlug,
        province: form.province,
        city_code: form.city_code,
        discount_code: discountCode,
      },
      token
    )
      .then((result) => {
        if (!cancelled) {
          setPreview(result);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setPreviewError(
            err instanceof Error
              ? err.message
              : 'محاسبه هزینه سفارش با خطا مواجه شد.'
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingPreview(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    items,
    token,
    form.province,
    form.city_code,
    selectedMethodSlug,
    discountCode,
    quoteRefreshKey,
  ]);

  const selectedMethod = shippingMethods.find(
    (m) => m.slug === selectedMethodSlug
  );

  const handleChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >
  ) => {
    const { name, value } = e.target;

    if (name === 'province') {
      setForm((f) => ({
        ...f,
        province: value,
        city_code: '',
      }));
      setError(null);
      return;
    }

    if (name === 'city_code') {
      setForm((f) => ({
        ...f,
        city_code: value,
      }));
      setError(null);
      return;
    }

    setForm((f) => ({ ...f, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!form.province) {
      return setError('استان را انتخاب کنید.');
    }

    if (!form.city_code) {
      return setError('شهر را انتخاب کنید.');
    }

    if (!form.address.trim() || form.address.trim().length < 10) {
      return setError('آدرس را کامل وارد کنید (حداقل ۱۰ کاراکتر).');
    }

    if (!selectedMethodSlug) {
      return setError('روش ارسال را انتخاب کنید.');
    }

    if (!/^09\d{9}$/.test(form.mobile)) {
      return setError('شماره موبایل معتبر نیست.');
    }

    if (!token) {
      return setError('ابتدا وارد حساب کاربری شوید.');
    }

    if (loadingPreview || !preview?.quote_token) {
      return setError(
        previewError || 'ابتدا باید محاسبه هزینه سفارش با موفقیت انجام شود.'
      );
    }

    if (!priceConfirmed) {
      return setError('لطفاً مبلغ نهایی و جزئیات قیمت را بررسی و تأیید کنید.');
    }

    setSubmitting(true);

    try {
      const response = await createOrder(
        {
          items: items.map((i) => ({
            variant_id: i.variantId,
            quantity: i.quantity,
          })),
          quote_token: preview.quote_token,
          shipping_method_slug: selectedMethodSlug,
          province: form.province,
          city_code: form.city_code,
          address: form.address,
          postal_code: form.postal_code,
          first_name: form.first_name,
          last_name: form.last_name,
          mobile: form.mobile,
          notes: form.notes,
        },
        token
      );

      // Keep the cart until payment succeeds.
      router.push(`/checkout/payment?order=${response.order_number}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'خطای نامشخص';
      setError(message);
      if (message.includes('پیش‌نمایش') || message.includes('قیمت') || message.includes('مبلغ نهایی') || message.includes('تخفیف') || message.includes('ظرفیت')) {
        setPriceConfirmed(false);
        setQuoteRefreshKey((current) => current + 1);
      }
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

  const formatPrice = (amount: number) =>
    amount.toLocaleString('fa-IR');

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
          <div className="lg:col-span-2 space-y-4">
            <div className="border border-rose-200 bg-rose-50/70 rounded-2xl p-4 shadow-sm">
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

            <div className="border border-sky-200 bg-sky-50/60 rounded-2xl p-4 shadow-sm">
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

                <select
                  name="city_code"
                  value={form.city_code}
                  onChange={handleChange}
                  required
                  disabled={!form.province || loadingCities || cities.length === 0}
                  className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pink-800 text-gray-900 bg-white disabled:bg-gray-100 disabled:text-gray-500"
                >
                  <option value="">
                    {!form.province
                      ? 'ابتدا استان را انتخاب کنید'
                      : loadingCities
                        ? 'در حال دریافت شهرها...'
                        : cities.length === 0
                          ? 'شهری برای این استان یافت نشد'
                          : 'انتخاب شهر *'}
                  </option>

                  {cities.map((city) => {
                    const details = [
                      city.county_name,
                      city.district_name,
                    ].filter(Boolean);

                    const label = details.length
                      ? `${city.name} (${details.join(' - ')})`
                      : city.name;

                    return (
                      <option key={city.code} value={city.code}>
                        {label}
                      </option>
                    );
                  })}
                </select>
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

            <div className="border border-violet-200 bg-violet-50/60 rounded-2xl p-4 shadow-sm">
              <h2 className="font-bold text-gray-800 mb-3">روش ارسال</h2>

              {!form.province ? (
                <p className="text-sm text-gray-500">
                  ابتدا استان را انتخاب کنید.
                </p>
              ) : !form.city_code ? (
                <p className="text-sm text-gray-500">
                  ابتدا شهر را انتخاب کنید.
                </p>
              ) : loadingMethods ? (
                <p className="text-sm text-gray-500">
                  در حال بارگذاری روش‌های ارسال...
                </p>
              ) : shippingMethods.length === 0 ? (
                <p className="text-sm text-red-600">
                  برای این شهر روش ارسالی تعریف نشده است.
                </p>
              ) : (
                <div className="space-y-2">
                  {shippingMethods.map((m) => (
                    <label
                      key={m.id}
                      className={`flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${
                        selectedMethodSlug === m.slug
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
                            {m.cost === null
                              ? 'تعرفه نامشخص'
                              : `${formatPrice(m.cost)} تومان`}
                          </span>
                        </div>

                        {m.description && (
                          <p className="text-xs text-gray-600 mt-1">
                            {m.description}
                          </p>
                        )}

                        <p className="text-xs text-gray-500 mt-1">
                          تعرفه پایه؛ مبلغ نهایی پس از محاسبه وزن و شرایط سفارش مشخص می‌شود.
                        </p>
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>

            <div className="border border-amber-200 bg-amber-50/60 rounded-2xl p-4 shadow-sm">
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

          <aside className="bg-rose-50/80 border border-rose-200 rounded-2xl p-6 h-fit sticky top-24 shadow-sm">
            <h2 className="font-bold text-pink-900 mb-4">خلاصه سفارش</h2>

            <div className="mb-4 rounded-xl border border-rose-200 bg-white/90 p-3 shadow-sm">
              <label htmlFor="discount-code" className="mb-2 block text-sm font-bold text-gray-800">
                کد تخفیف
              </label>
              <div className="flex gap-2">
                <input
                  id="discount-code"
                  value={discountCodeInput}
                  onChange={(event) => setDiscountCodeInput(event.target.value.toUpperCase())}
                  placeholder="کد تخفیف را وارد کنید"
                  maxLength={40}
                  dir="ltr"
                  className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900"
                />
                <button
                  type="button"
                  disabled={loadingPreview || !discountCodeInput.trim()}
                  onClick={() => {
                    setDiscountCode(discountCodeInput.trim().toUpperCase());
                    setPriceConfirmed(false);
                    setError(null);
                  }}
                  className="rounded-lg bg-pink-800 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
                >
                  اعمال
                </button>
                {discountCode && (
                  <button
                    type="button"
                    disabled={loadingPreview}
                    onClick={() => {
                      setDiscountCode('');
                      setDiscountCodeInput('');
                      setPriceConfirmed(false);
                    }}
                    className="rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50"
                  >
                    حذف
                  </button>
                )}
              </div>
              {discountCode && (
                <p className="mt-2 text-xs text-gray-600" dir="ltr">
                  {discountCode}
                </p>
              )}
            </div>

            <div className="space-y-2 mb-4 max-h-64 overflow-y-auto">
              {items.map((i) => (
                <div
                  key={i.variantId}
                  className="flex justify-between text-xs text-gray-700"
                >
                  <span className="truncate ml-2">
                    {i.productName} × {i.quantity}
                    {preview?.items.some((quoted) => quoted.variant_id === i.variantId && quoted.unit_price !== i.price) && (
                      <span className="mr-1 text-amber-700"> (قیمت به‌روز)</span>
                    )}
                  </span>

                  <span className="whitespace-nowrap font-medium">
                    {formatPrice(
                      preview?.items.find((quoted) => quoted.variant_id === i.variantId)?.line_subtotal
                      ?? i.price * i.quantity
                    )}
                  </span>
                </div>
              ))}
            </div>

            <div className="space-y-2 text-sm border-t border-pink-300 pt-3">
              <div className="flex justify-between">
                <span className="text-gray-700">جمع کالاها</span>
                <span className="font-semibold text-gray-900">
                  {preview ? formatPrice(preview.subtotal) : '—'}
                </span>
              </div>

              {preview && preview.discount_amount > 0 && (
                <div className="space-y-1 rounded-lg bg-green-50 p-3 text-sm">
                  <div className="flex justify-between font-bold text-green-800">
                    <span>تخفیف</span>
                    <span>−{formatPrice(preview.discount_amount)} تومان</span>
                  </div>
                  {preview.discounts.map((discount) => (
                    <div key={discount.campaign_id} className="flex justify-between gap-2 text-xs text-green-800">
                      <span>{discount.name}</span>
                      <span className="whitespace-nowrap">−{formatPrice(discount.discount_amount)}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex justify-between">
                <span className="text-gray-700">مالیات</span>
                <span className="font-semibold text-gray-900">
                  {preview ? formatPrice(preview.vat_amount) : '—'}
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-gray-700">هزینه ارسال</span>
                <span
                  className={`font-semibold ${
                    preview?.shipping_cost === 0
                      ? 'text-green-700'
                      : 'text-gray-900'
                  }`}
                >
                  {!preview
                    ? '—'
                    : preview.shipping.is_free
                      ? 'رایگان'
                      : formatPrice(preview.shipping_cost)}
                </span>
              </div>

              <div className="flex justify-between">
                <span className="text-gray-700">هزینه بسته‌بندی</span>
                <span
                  className={`font-semibold ${
                    preview?.packaging_cost === 0
                      ? 'text-green-700'
                      : 'text-gray-900'
                  }`}
                >
                  {!preview
                    ? '—'
                    : preview.packaging.is_free
                      ? 'رایگان'
                      : formatPrice(preview.packaging_cost)}
                </span>
              </div>

              {loadingPreview && (
                <p className="text-xs text-gray-500">
                  در حال محاسبه هزینه‌های سفارش...
                </p>
              )}

              {previewError && (
                <p className="text-xs text-red-600">
                  {previewError}
                </p>
              )}

              <div className="border-t border-pink-300 pt-3 flex justify-between">
                <span className="font-bold text-gray-900">مبلغ نهایی</span>
                <span className="font-bold text-pink-900 text-lg">
                  {preview
                    ? `${formatPrice(preview.total_amount)} تومان`
                    : '—'}
                </span>
              </div>
            </div>

            {preview?.quote_token && (
              <label className="mt-4 flex items-start gap-2 rounded-lg border border-pink-200 bg-white p-3 text-xs leading-6 text-gray-700">
                <input
                  type="checkbox"
                  checked={priceConfirmed}
                  onChange={(event) => setPriceConfirmed(event.target.checked)}
                  className="mt-1 accent-pink-800"
                />
                <span>
                  مبلغ نهایی، قیمت روز کالاها، مالیات و هزینه‌های ارسال و بسته‌بندی را بررسی کردم و تأیید می‌کنم.
                  <span className="block text-gray-500">اعتبار این پیش‌نمایش ۱۰ دقیقه است؛ پس از تغییر سبد یا اطلاعات ارسال باید دوباره تأیید کنید.</span>
                </span>
              </label>
            )}

            {error && (
              <div className="mt-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={
                submitting ||
                loadingCities ||
                loadingMethods ||
                loadingPreview ||
                !form.city_code ||
                !selectedMethodSlug ||
                !preview ||
                !priceConfirmed
              }
              className="w-full mt-4 bg-pink-800 hover:bg-pink-900 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition-colors"
            >
              {submitting
                ? 'در حال ثبت سفارش...'
                : loadingPreview
                  ? 'در حال محاسبه هزینه...'
                  : 'ثبت سفارش'}
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
