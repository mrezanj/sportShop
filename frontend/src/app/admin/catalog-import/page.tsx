'use client';

import { useState, type FormEvent } from 'react';
import { useAuth } from '@/context/AuthContext';

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const inputClass = 'w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-pink-500';

type ImportResult = {
  success: boolean;
  rows_processed: number;
  products_created: number;
  products_updated: number;
  variants_created: number;
  variants_updated: number;
  price_history_entries: number;
};

export default function CatalogImportPage() {
  const { token, user, loading: authLoading } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<ImportResult | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token || !file) {
      setError('فایل CSV یا XLSX را انتخاب کنید.');
      return;
    }
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const body = new FormData();
      body.append('file', file);
      const response = await fetch(`${API_URL}/products/import-catalog/`, {
        method: 'POST',
        headers: { Authorization: `Token ${token}` },
        body,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message = data?.file?.[0] || data?.detail || 'ورود کاتالوگ انجام نشد.';
        throw new Error(message);
      }
      setResult(data as ImportResult);
      setFile(null);
      const input = document.getElementById('catalog-import-file') as HTMLInputElement | null;
      if (input) input.value = '';
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ورود کاتالوگ انجام نشد.');
    } finally {
      setBusy(false);
    }
  };

  if (authLoading) return <main className="grid min-h-[60vh] place-items-center">در حال بررسی دسترسی...</main>;
  if (!user || !token) return <main className="container mx-auto px-4 py-16 text-center">برای ورود به مدیریت کاتالوگ ابتدا وارد حساب کاربری شوید.</main>;
  if (!user.is_staff) return <main className="container mx-auto px-4 py-16 text-center text-amber-800">این بخش فقط برای کاربران داخلی فروشگاه است.</main>;

  return (
    <main className="min-h-screen bg-page py-8" dir="rtl">
      <div className="container mx-auto max-w-5xl space-y-6 px-4">
        <header>
          <p className="section-label">مدیریت فروشگاه</p>
          <h1 className="text-3xl font-bold text-pink-950">ورود گروهی کاتالوگ</h1>
          <p className="mt-2 text-sm text-gray-600">ایجاد یا به‌روزرسانی محصول و تنوع از فایل CSV یا Excel</p>
          <nav className="mt-4 flex flex-wrap gap-2">
            <a href="/admin/pricing" className="rounded-xl border border-pink-200 bg-white px-4 py-2 text-sm font-bold text-pink-900">مدیریت قیمت‌ها</a>
            <a href="/admin/inventory" className="rounded-xl border border-pink-200 bg-white px-4 py-2 text-sm font-bold text-pink-900">مدیریت موجودی</a>
          </nav>
        </header>

        {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
        {result && (
          <section role="status" className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
            <h2 className="font-bold text-emerald-900">ورود فایل با موفقیت انجام شد</h2>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
              <Metric label="ردیف پردازش‌شده" value={result.rows_processed} />
              <Metric label="محصول جدید" value={result.products_created} />
              <Metric label="محصول به‌روزشده" value={result.products_updated} />
              <Metric label="تنوع جدید" value={result.variants_created} />
              <Metric label="تنوع به‌روزشده" value={result.variants_updated} />
              <Metric label="ثبت سابقه قیمت" value={result.price_history_entries} />
            </div>
          </section>
        )}

        <form onSubmit={submit} className="space-y-5 rounded-2xl border border-pink-100 bg-white p-5 shadow-sm">
          <div>
            <h2 className="text-xl font-bold text-gray-900">انتخاب فایل</h2>
            <p className="mt-1 text-sm leading-7 text-gray-600">فایل حداکثر ۲ مگابایت و ۵۰۰۰ ردیف داده داشته باشد. تمام ردیف‌ها پیش از ثبت بررسی می‌شوند و اگر یک ردیف نامعتبر باشد، هیچ تغییری ذخیره نمی‌شود.</p>
          </div>
          <label className="block space-y-2 text-sm font-medium text-gray-700">
            فایل CSV یا XLSX
            <input id="catalog-import-file" type="file" accept=".csv,.xlsx" className={inputClass} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </label>
          {file && <p className="text-xs text-gray-500">{file.name}</p>}
          <button disabled={busy || !file} className="w-full rounded-xl bg-pink-800 px-4 py-3 font-bold text-white disabled:opacity-50">{busy ? 'در حال اعتبارسنجی و ورود...' : 'اعتبارسنجی و ورود کاتالوگ'}</button>
        </form>

        <section className="rounded-2xl border border-pink-100 bg-white p-5">
          <h2 className="text-lg font-bold text-gray-900">قالب فایل</h2>
          <p className="mt-2 text-sm leading-7 text-gray-600">هر ردیف یک تنوع محصول است. برای ثبت چند طعم یا وزن از یک محصول، اطلاعات محصول را در هر ردیف تکرار و SKU متفاوت وارد کنید. برای به‌روزرسانی تنوع موجود، SKU قبلی را بنویسید.</p>
          <div className="mt-3 overflow-x-auto rounded-lg bg-gray-50 p-3">
            <code dir="ltr" className="block min-w-max text-xs leading-7">product_slug,name_fa,brand_slug,category_slug,description,price,sku,flavor,weight,size,color,servings,attributes,consumption_goals,minimum_age,requires_cold_shipping</code>
          </div>
          <p className="mt-3 text-xs leading-6 text-gray-500">ستون‌های product_slug، name_fa، brand_slug، category_slug، description و price الزامی هستند. شناسه برند و دسته باید slug فعال آن‌ها باشد. attributes و consumption_goals به‌صورت JSON معتبر وارد شوند. ستون stock پذیرفته نمی‌شود؛ موجودی فقط از طریق اسناد انبار تغییر می‌کند. فیلدهای خالی در به‌روزرسانی، اطلاعات قبلی را حفظ می‌کنند.</p>
          <p className="mt-2 text-xs leading-6 text-gray-500">تصاویر محصول، بچ و تاریخ انقضا از این فایل وارد نمی‌شوند و باید از مسیرهای اختصاصی خود مدیریت شوند. قیمت‌های جدید یا تغییرکرده در سابقه قیمت ثبت خواهند شد.</p>
        </section>
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-xl bg-white/80 p-3"><p className="text-xs text-gray-600">{label}</p><p className="mt-1 text-xl font-bold text-emerald-900">{value.toLocaleString('fa-IR')}</p></div>;
}
