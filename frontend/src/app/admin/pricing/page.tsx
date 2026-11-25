'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useAuth } from '@/context/AuthContext';
import {
  bulkUpdateProductPrices,
  fetchProductPriceHistory,
  importProductPrices,
  type ProductPriceHistoryRow,
  type ProductPriceUpdateResult,
} from '@/lib/api';

const number = (value: number | string | null) =>
  value === null ? '—' : Number(value).toLocaleString('fa-IR');

const inputClass = 'w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-pink-500';

function normalizeDigits(value: string) {
  return value
    .replace(/[۰-۹]/g, (digit) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit)))
    .replace(/[٬,\s]/g, '');
}

export default function PricingAdminPage() {
  const { token, user, loading: authLoading } = useAuth();
  const [mode, setMode] = useState<'fixed' | 'increase_percent' | 'decrease_percent'>('fixed');
  const [rowsText, setRowsText] = useState('');
  const [note, setNote] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [history, setHistory] = useState<ProductPriceHistoryRow[]>([]);
  const [historySku, setHistorySku] = useState('');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [result, setResult] = useState<ProductPriceUpdateResult | null>(null);

  const loadHistory = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      setHistory(await fetchProductPriceHistory(token, historySku));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'دریافت سوابق قیمت انجام نشد.');
    } finally {
      setLoading(false);
    }
  }, [token, historySku]);

  useEffect(() => {
    if (token && user?.is_staff) void loadHistory();
  }, [token, user, loadHistory]);

  const submitBulk = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) return;
    const rows = rowsText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    const items: { sku: string; value: number }[] = [];
    for (const [index, line] of rows.entries()) {
      const [skuRaw, valueRaw] = line.split(/[;,\t]/, 2);
      const sku = (skuRaw || '').trim();
      const value = Number(normalizeDigits(valueRaw || ''));
      if (!sku || !Number.isFinite(value) || value <= 0) {
        setError(`ساختار ردیف ${index + 1} معتبر نیست. قالب هر خط: SKU, مقدار`);
        return;
      }
      items.push({ sku, value });
    }
    if (!items.length) {
      setError('حداقل یک SKU و مقدار قیمت وارد کنید.');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    setResult(null);
    try {
      const response = await bulkUpdateProductPrices(token, { mode, items, note });
      setResult(response);
      setRowsText('');
      setNotice(`${number(response.updated_count)} قیمت با موفقیت به‌روزرسانی شد.`);
      await loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'به‌روزرسانی قیمت انجام نشد.');
    } finally {
      setBusy(false);
    }
  };

  const submitImport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token || !file) {
      setError('فایل CSV یا XLSX را انتخاب کنید.');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    setResult(null);
    try {
      const response = await importProductPrices(token, file);
      setResult(response);
      setFile(null);
      setNotice(`ورود فایل انجام شد؛ ${number(response.updated_count)} قیمت تغییر کرد.`);
      await loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ورود فایل انجام نشد.');
    } finally {
      setBusy(false);
    }
  };

  if (authLoading) {
    return <main className="grid min-h-[60vh] place-items-center text-pink-900">در حال بررسی دسترسی...</main>;
  }
  if (!user || !token) {
    return <main className="container mx-auto px-4 py-16 text-center">برای ورود به مدیریت قیمت ابتدا وارد حساب کاربری شوید.</main>;
  }
  if (!user.is_staff) {
    return <main className="container mx-auto px-4 py-16 text-center text-amber-800">این بخش فقط برای کاربران داخلی فروشگاه است.</main>;
  }

  return (
    <main className="min-h-screen bg-page py-8" dir="rtl">
      <div className="container mx-auto max-w-7xl space-y-6 px-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="section-label">مدیریت فروشگاه</p>
            <h1 className="text-3xl font-bold text-pink-950">قیمت‌گذاری محصولات</h1>
            <p className="mt-2 text-sm text-gray-600">تغییر قیمت SKU، ورود گروهی و مشاهده سابقه تغییرات</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href="/admin/catalog-import" className="rounded-xl border border-pink-200 bg-white px-4 py-2.5 text-sm font-bold text-pink-900">ورود گروهی کاتالوگ</a>
            <a href="/admin/discounts" className="rounded-xl border border-pink-200 bg-white px-4 py-2.5 text-sm font-bold text-pink-900">مدیریت تخفیف‌ها</a>
            <a href="/admin/inventory" className="rounded-xl border border-pink-200 bg-white px-4 py-2.5 text-sm font-bold text-pink-900">داشبورد انبار</a>
            <a href="/admin/returns-refunds" className="rounded-xl border border-pink-200 bg-white px-4 py-2.5 text-sm font-bold text-pink-900">مرجوعی و بازپرداخت</a>
          </div>
        </header>

        {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
        {notice && <div role="status" className="rounded-xl border border-green-200 bg-green-50 p-3 text-sm text-green-800">{notice}</div>}

        <section className="grid gap-6 lg:grid-cols-2">
          <form onSubmit={submitBulk} className="space-y-4 rounded-2xl border border-pink-100 bg-white p-5 shadow-sm">
            <div>
              <h2 className="text-xl font-bold text-gray-900">تغییر دستی یا گروهی قیمت</h2>
              <p className="mt-1 text-xs leading-6 text-gray-500">هر خط یک SKU و مقدار دارد. جداکننده می‌تواند کاما، سمی‌کالن یا Tab باشد.</p>
            </div>
            <label className="block space-y-2 text-sm font-medium text-gray-700">
              نوع تغییر
              <select className={inputClass} value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
                <option value="fixed">ثبت قیمت جدید (تومان)</option>
                <option value="increase_percent">افزایش درصدی</option>
                <option value="decrease_percent">کاهش درصدی</option>
              </select>
            </label>
            <label className="block space-y-2 text-sm font-medium text-gray-700">
              SKU و مقدار
              <textarea className={inputClass + ' min-h-36 font-mono'} value={rowsText} onChange={(event) => setRowsText(event.target.value)} placeholder={'SKU-001,125000\nSKU-002,10'} />
            </label>
            <label className="block space-y-2 text-sm font-medium text-gray-700">
              توضیح تغییر (اختیاری)
              <input className={inputClass} value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} />
            </label>
            <button disabled={busy} className="w-full rounded-xl bg-pink-800 px-4 py-3 font-bold text-white disabled:opacity-50">{busy ? 'در حال پردازش...' : 'اعمال تغییر قیمت'}</button>
          </form>

          <form onSubmit={submitImport} className="space-y-4 rounded-2xl border border-pink-100 bg-white p-5 shadow-sm">
            <div>
              <h2 className="text-xl font-bold text-gray-900">ورود قیمت از فایل Excel یا CSV</h2>
              <p className="mt-1 text-xs leading-6 text-gray-500">فایل باید ستون‌های sku و price داشته باشد. حداکثر ۵۰۰۰ ردیف و ۲ مگابایت.</p>
            </div>
            <div className="rounded-xl bg-pink-50 p-4 text-sm leading-7 text-pink-950">
              <p className="font-bold">قالب فایل</p>
              <p dir="ltr">sku,price</p>
              <p dir="ltr">SKU-001,125000</p>
              <p dir="ltr">SKU-002,250000</p>
              <p className="mt-2 text-xs text-gray-600">فایل XLSX یا CSV با کدگذاری UTF-8 پذیرفته می‌شود؛ فایل قدیمی XLS پشتیبانی نمی‌شود.</p>
            </div>
            <label className="block space-y-2 text-sm font-medium text-gray-700">
              انتخاب فایل
              <input type="file" accept=".csv,.xlsx" className={inputClass} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            </label>
            {file && <p className="text-xs text-gray-600">{file.name}</p>}
            <button disabled={busy || !file} className="w-full rounded-xl border border-pink-300 bg-white px-4 py-3 font-bold text-pink-900 disabled:opacity-50">{busy ? 'در حال پردازش...' : 'اعتبارسنجی و ورود فایل'}</button>
          </form>
        </section>

        {result && (
          <section className="rounded-2xl border border-pink-100 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-lg font-bold">نتیجه آخرین عملیات</h2>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <thead><tr className="border-b text-right text-gray-500"><th className="p-2">SKU</th><th className="p-2">قیمت قبلی</th><th className="p-2">قیمت جدید</th></tr></thead>
                <tbody>{result.items.map((item) => <tr key={item.sku} className="border-b border-gray-50"><td className="p-2 font-mono" dir="ltr">{item.sku}</td><td className="p-2">{number(item.old_price)}</td><td className="p-2 font-bold text-pink-900">{number(item.new_price)}</td></tr>)}</tbody>
              </table>
            </div>
          </section>
        )}

        <section className="rounded-2xl border border-pink-100 bg-white p-5 shadow-sm">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div><h2 className="text-xl font-bold text-gray-900">سوابق تغییر قیمت</h2><p className="mt-1 text-xs text-gray-500">۱۰۰ تغییر اخیر؛ فقط کاربران دارای مجوز مدیریت قیمت به این اطلاعات دسترسی دارند.</p></div>
            <div className="flex gap-2">
              <input className={inputClass + ' min-w-48'} value={historySku} onChange={(event) => setHistorySku(event.target.value)} placeholder="جست‌وجو با SKU" />
              <button type="button" onClick={() => void loadHistory()} className="rounded-xl border border-pink-200 px-4 py-2 text-sm font-bold text-pink-900">جست‌وجو</button>
            </div>
          </div>
          {loading ? <p className="py-8 text-center text-sm text-gray-500">در حال دریافت سوابق...</p> : history.length === 0 ? <p className="py-8 text-center text-sm text-gray-500">سابقه‌ای یافت نشد یا مجوز مشاهده ندارید.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-sm">
                <thead><tr className="border-b text-right text-gray-500"><th className="p-2">زمان</th><th className="p-2">محصول / SKU</th><th className="p-2">قیمت قبلی</th><th className="p-2">قیمت جدید</th><th className="p-2">نوع تغییر</th><th className="p-2">کاربر</th></tr></thead>
                <tbody>{history.map((row) => <tr key={row.id} className="border-b border-gray-50"><td className="p-2 whitespace-nowrap">{new Date(row.created_at).toLocaleString('fa-IR')}</td><td className="p-2"><div>{row.product_name}</div><div className="font-mono text-xs text-gray-500" dir="ltr">{row.sku}</div></td><td className="p-2">{number(row.old_price)}</td><td className="p-2 font-bold text-pink-900">{number(row.new_price)}</td><td className="p-2">{row.change_type === 'import' ? 'ورود فایل' : row.change_type === 'manual' ? 'دستی' : 'گروهی'}</td><td className="p-2">{row.changed_by__username ?? '—'}</td></tr>)}</tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
