'use client';

import { useState, type FormEvent } from 'react';
import { useAuth } from '@/context/AuthContext';

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const inputClass = 'w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-pink-500';

type Result = {
  success: boolean;
  document_id: number;
  document_number: string;
  status: string;
  rows_processed: number;
};

export default function InventoryImportPage() {
  const { token, user, loading: authLoading } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [documentNumber, setDocumentNumber] = useState('');
  const [reference, setReference] = useState('');
  const [reason, setReason] = useState('ورود گروهی موجودی');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<Result | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token || !file || !documentNumber.trim()) {
      setError('شماره سند و فایل را وارد کنید.');
      return;
    }
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const body = new FormData();
      body.append('file', file);
      body.append('document_number', documentNumber.trim());
      body.append('reference', reference.trim());
      body.append('reason', reason.trim());
      const response = await fetch(`${API_URL}/inventory/import/`, {
        method: 'POST',
        headers: { Authorization: `Token ${token}` },
        body,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message = data?.detail || data?.file?.[0] || data?.sku?.[0] ||
          Object.values(data ?? {}).flat().find(value => typeof value === 'string') ||
          'ورود گروهی موجودی انجام نشد.';
        throw new Error(String(message));
      }
      setResult(data as Result);
      setFile(null);
      const input = document.getElementById('inventory-import-file') as HTMLInputElement | null;
      if (input) input.value = '';
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ورود گروهی موجودی انجام نشد.');
    } finally {
      setBusy(false);
    }
  };

  if (authLoading) return <main className="grid min-h-[60vh] place-items-center">در حال بررسی دسترسی...</main>;
  if (!user || !token) return <main className="container mx-auto px-4 py-16 text-center">برای ورود به مدیریت انبار ابتدا وارد حساب کاربری شوید.</main>;
  if (!user.is_staff) return <main className="container mx-auto px-4 py-16 text-center text-amber-800">این بخش فقط برای کاربران داخلی فروشگاه است.</main>;

  return (
    <main className="min-h-screen bg-page py-8" dir="rtl">
      <div className="container mx-auto max-w-5xl space-y-6 px-4">
        <header>
          <p className="section-label">مدیریت فروشگاه</p>
          <h1 className="text-3xl font-bold text-pink-950">ورود گروهی موجودی</h1>
          <p className="mt-2 text-sm text-gray-600">ثبت چند SKU و بچ در قالب یک سند پیش‌نویس انبار</p>
          <nav className="mt-4 flex flex-wrap gap-2">
            <a href="/admin/inventory" className="rounded-xl border border-pink-200 bg-white px-4 py-2 text-sm font-bold text-pink-900">داشبورد انبار</a>
            <a href="/admin/catalog-import" className="rounded-xl border border-pink-200 bg-white px-4 py-2 text-sm font-bold text-pink-900">ورود کاتالوگ</a>
          </nav>
        </header>

        {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
        {result && (
          <section role="status" className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
            <h2 className="font-bold text-emerald-900">فایل اعتبارسنجی و سند پیش‌نویس ایجاد شد</h2>
            <p className="mt-2 text-sm text-emerald-900">شماره سند: {result.document_number}</p>
            <p className="mt-1 text-sm text-emerald-900">تعداد ردیف: {result.rows_processed.toLocaleString('fa-IR')}</p>
            <a href="/admin/inventory" className="mt-3 inline-flex rounded-xl bg-pink-800 px-4 py-2 font-bold text-white">مشاهده سند در داشبورد انبار</a>
          </section>
        )}

        <form onSubmit={submit} className="space-y-5 rounded-2xl border border-pink-100 bg-white p-5 shadow-sm">
          <div>
            <h2 className="text-xl font-bold text-gray-900">مشخصات سند</h2>
            <p className="mt-1 text-sm leading-7 text-gray-600">فایل حداکثر ۲ مگابایت و ۵۰۰۰ ردیف داده داشته باشد. تمام ردیف‌ها قبل از ایجاد سند بررسی می‌شوند؛ در صورت وجود خطا هیچ سند یا موجودی‌ای ثبت نخواهد شد.</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-2 text-sm font-medium text-gray-700">شماره سند
              <input required value={documentNumber} onChange={event => setDocumentNumber(event.target.value)} className={inputClass} maxLength={50} />
            </label>
            <label className="space-y-2 text-sm font-medium text-gray-700">شماره مرجع / فاکتور تأمین‌کننده
              <input value={reference} onChange={event => setReference(event.target.value)} className={inputClass} maxLength={100} />
            </label>
          </div>
          <label className="block space-y-2 text-sm font-medium text-gray-700">دلیل عملیات
            <input value={reason} onChange={event => setReason(event.target.value)} className={inputClass} />
          </label>
          <label className="block space-y-2 text-sm font-medium text-gray-700">فایل CSV یا XLSX
            <input id="inventory-import-file" required type="file" accept=".csv,.xlsx" className={inputClass} onChange={event => setFile(event.target.files?.[0] ?? null)} />
          </label>
          {file && <p className="text-xs text-gray-500">{file.name}</p>}
          <button disabled={busy || !file || !documentNumber.trim()} className="w-full rounded-xl bg-pink-800 px-4 py-3 font-bold text-white disabled:opacity-50">{busy ? 'در حال اعتبارسنجی و ثبت پیش‌نویس...' : 'اعتبارسنجی و ایجاد سند پیش‌نویس'}</button>
        </form>

        <section className="rounded-2xl border border-pink-100 bg-white p-5">
          <h2 className="text-lg font-bold text-gray-900">قالب فایل</h2>
          <p className="mt-2 text-sm leading-7 text-gray-600">هر ردیف معرف یک SKU و یک بچ است. برای افزودن چند بچ به یک SKU، SKU را در چند ردیف تکرار کنید؛ ترکیب SKU و شماره بچ نباید در فایل تکراری باشد.</p>
          <div className="mt-3 overflow-x-auto rounded-lg bg-gray-50 p-3">
            <code dir="ltr" className="block min-w-max text-xs leading-7">sku,quantity,batch_number,expiration_date,unit_cost,reason</code>
          </div>
          <ul className="mt-3 list-disc space-y-1 pr-5 text-xs leading-6 text-gray-600">
            <li>ستون‌های sku، quantity و batch_number الزامی‌اند.</li>
            <li>تاریخ انقضا اختیاری و با قالب YYYY-MM-DD است.</li>
            <li>unit_cost اختیاری و به تومان، عدد صحیح غیرمنفی است.</li>
            <li>SKU باید از قبل در کاتالوگ وجود داشته باشد.</li>
            <li>بچ موجود با همان SKU و شماره بچ به همان بچ متصل می‌شود؛ تاریخ انقضای مغایر پذیرفته نمی‌شود.</li>
            <li>ورود فایل فقط سند خریدِ پیش‌نویس می‌سازد. موجودی تا بررسی حسابدار و تأیید مدیر داخلی تغییر نمی‌کند.</li>
            <li>خروجی این مسیر فقط موجودی ورودی است؛ خروج، ضایعات و اصلاح همچنان از اسناد عادی انبار انجام می‌شوند.</li>
          </ul>
        </section>
      </div>
    </main>
  );
}
