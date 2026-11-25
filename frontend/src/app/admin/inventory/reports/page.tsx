'use client';

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/context/AuthContext';
import {
  fetchInventoryBatchReport,
  fetchInventoryMovementReport,
  type InventoryBatchReportRow,
  type InventoryMovementReportRow,
} from '@/lib/api';

const number = (value: number) => new Intl.NumberFormat('fa-IR').format(value);
const date = (value: string | null) => value
  ? new Date(value).toLocaleDateString('fa-IR')
  : '—';
const dateTime = (value: string) => new Date(value).toLocaleString('fa-IR');
const inputClass = 'w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-pink-500';

export default function InventoryReportsPage() {
  const { token, user, loading: authLoading } = useAuth();
  const [tab, setTab] = useState<'batches' | 'movements'>('batches');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [movementType, setMovementType] = useState('');
  const [page, setPage] = useState(1);
  const [batchData, setBatchData] = useState<{count:number;results:InventoryBatchReportRow[];next:string|null;previous:string|null} | null>(null);
  const [movementData, setMovementData] = useState<{count:number;results:InventoryMovementReportRow[];next:string|null;previous:string|null} | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      if (tab === 'batches') {
        const data = await fetchInventoryBatchReport(token, { page, search, status, page_size: 25 });
        setBatchData(data);
      } else {
        const data = await fetchInventoryMovementReport(token, {
          page, search, movement_type: movementType, page_size: 25,
        });
        setMovementData(data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'دریافت گزارش انبار ناموفق بود.');
    } finally {
      setLoading(false);
    }
  }, [token, tab, page, search, status, movementType]);

  useEffect(() => {
    if (token) void load();
  }, [token, load]);

  const changeTab = (value: 'batches' | 'movements') => {
    setTab(value);
    setPage(1);
    setSearch('');
    setStatus('');
    setMovementType('');
  };

  if (authLoading) return <div className="min-h-[50vh] grid place-items-center">در حال بررسی دسترسی...</div>;
  if (!user || !token) return <main className="container mx-auto px-4 py-16 text-center">برای مشاهده گزارش انبار وارد حساب شوید. <a className="text-pink-800 underline" href="/login">ورود</a></main>;
  if (!user.is_staff) return <main className="container mx-auto px-4 py-16 text-center">این بخش فقط برای کارکنان فروشگاه در دسترس است.</main>;

  const currentCount = tab === 'batches' ? batchData?.count ?? 0 : movementData?.count ?? 0;
  const hasPrevious = tab === 'batches' ? !!batchData?.previous : !!movementData?.previous;
  const hasNext = tab === 'batches' ? !!batchData?.next : !!movementData?.next;

  return (
    <main className="min-h-screen bg-page py-8 sm:py-10">
      <div className="container mx-auto max-w-7xl space-y-6 px-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="section-label">مدیریت عملیات فروشگاه</p>
            <h1 className="text-3xl sm:text-4xl">گزارش‌های انبار</h1>
            <p className="mt-2 text-sm text-gray-500">موجودی بچ‌ها و دفترکل تغییرات موجودی</p>
          </div>
          <a href="/admin/inventory" className="rounded-xl border border-pink-200 bg-white px-4 py-2.5 text-sm font-bold text-pink-900">بازگشت به داشبورد انبار</a>
        </header>

        <div className="flex flex-wrap gap-2">
          <button onClick={() => changeTab('batches')} className={tab === 'batches' ? 'rounded-xl bg-pink-800 px-4 py-2.5 text-sm font-bold text-white' : 'rounded-xl border bg-white px-4 py-2.5 text-sm'}>موجودی بچ‌ها</button>
          <button onClick={() => changeTab('movements')} className={tab === 'movements' ? 'rounded-xl bg-pink-800 px-4 py-2.5 text-sm font-bold text-white' : 'rounded-xl border bg-white px-4 py-2.5 text-sm'}>گردش‌های دفترکل</button>
        </div>

        <section className="rounded-2xl border border-pink-100 bg-white p-4 shadow-sm sm:p-6">
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <input className={inputClass} value={search} onChange={e => {setSearch(e.target.value);setPage(1);}} placeholder={tab === 'batches' ? 'جست‌وجوی SKU، کالا یا شماره بچ' : 'جست‌وجوی SKU، بچ، سند یا توضیحات'} />
            {tab === 'batches' ? (
              <select className={inputClass} value={status} onChange={e => {setStatus(e.target.value);setPage(1);}}>
                <option value="">همه وضعیت بچ‌ها</option>
                <option value="available">قابل فروش</option>
                <option value="quarantined">قرنطینه</option>
                <option value="blocked">غیرقابل فروش</option>
              </select>
            ) : (
              <select className={inputClass} value={movementType} onChange={e => {setMovementType(e.target.value);setPage(1);}}>
                <option value="">همه گردش‌ها</option>
                <option value="inbound">ورود</option>
                <option value="outbound">خروج</option>
                <option value="return">مرجوعی</option>
                <option value="waste">ضایعات</option>
                <option value="adjustment">اصلاح موجودی</option>
                <option value="reversal">گردش معکوس</option>
              </select>
            )}
            <button onClick={() => void load()} disabled={loading} className="rounded-xl border border-pink-200 bg-white px-4 py-2.5 text-sm font-bold text-pink-900 disabled:opacity-50">{loading ? 'در حال دریافت...' : 'به‌روزرسانی گزارش'}</button>
          </div>

          {error && <div role="alert" className="mb-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
          <div className="mb-3 text-sm text-gray-500">تعداد نتایج: {number(currentCount)}</div>

          {tab === 'batches' ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1050px] text-sm">
                <thead><tr className="border-b text-right text-gray-500">
                  <th className="p-3">SKU / کالا</th><th className="p-3">شماره بچ</th><th className="p-3">وضعیت</th><th className="p-3">انقضا</th><th className="p-3">فیزیکی</th><th className="p-3">رزرو</th><th className="p-3">قابل فروش</th><th className="p-3">ثبت‌کننده سند / ایجادکننده بچ</th>
                </tr></thead>
                <tbody>
                  {(batchData?.results ?? []).map((row: InventoryBatchReportRow) => <tr key={row.id} className="border-b border-gray-50">
                    <td className="p-3"><strong>{row.sku}</strong><span className="block text-xs text-gray-500">{row.product_name} · {row.brand_name}</span></td>
                    <td className="p-3 font-mono">{row.batch_number}</td>
                    <td className="p-3"><span className={row.is_expired ? 'text-red-700' : 'text-gray-700'}>{row.is_expired ? 'منقضی' : row.status_display}</span></td>
                    <td className="p-3">{date(row.expiration_date)}</td><td className="p-3 tabular-nums">{number(row.physical)}</td><td className="p-3 tabular-nums">{number(row.reserved)}</td><td className="p-3 tabular-nums font-bold">{number(row.available)}</td>
                    <td className="p-3">{row.document_created_by_display ?? '—'}<span className="block text-xs text-gray-500">ثبت‌کننده سند{row.document_created_by_role ? ` · ${row.document_created_by_role}` : ''}</span><span className="mt-1 block text-xs text-gray-400">ایجادکننده بچ: {row.created_by_display ?? '—'}{row.created_by_role ? ` · ${row.created_by_role}` : ''}</span></td>
                  </tr>)}
                  {!loading && (batchData?.results.length ?? 0) === 0 && <tr><td colSpan={8} className="p-8 text-center text-gray-500">بچی برای نمایش پیدا نشد.</td></tr>}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1250px] text-sm">
                <thead><tr className="border-b text-right text-gray-500">
                  <th className="p-3">تاریخ</th><th className="p-3">SKU</th><th className="p-3">بچ</th><th className="p-3">نوع گردش</th><th className="p-3">تغییر تعداد</th><th className="p-3">شماره سند</th><th className="p-3">وضعیت سند</th><th className="p-3">بهای واحد (تومان)</th><th className="p-3">ثبت‌کننده سند / انجام‌دهنده گردش</th>
                </tr></thead>
                <tbody>
                  {(movementData?.results ?? []).map((row: InventoryMovementReportRow) => <tr key={row.id} className="border-b border-gray-50">
                    <td className="p-3 whitespace-nowrap">{dateTime(row.created_at)}</td><td className="p-3">{row.sku}<span className="block text-xs text-gray-500">{row.product_name}</span></td><td className="p-3 font-mono">{row.batch_number}</td><td className="p-3">{row.movement_type_display}</td>
                    <td className={'p-3 font-bold tabular-nums ' + (row.quantity_delta > 0 ? 'text-green-700' : 'text-red-700')}>{row.quantity_delta > 0 ? '+' : ''}{number(row.quantity_delta)}</td>
                    <td className="p-3">{row.document_number}<span className="block text-xs text-gray-500">{row.document_type_display}</span></td><td className="p-3">{row.document_status_display}</td><td className="p-3 tabular-nums">{row.unit_cost === null ? '—' : number(Number(row.unit_cost))}</td>
                    <td className="p-3">{row.document_created_by_display ?? '—'}<span className="block text-xs text-gray-500">ثبت‌کننده سند{row.document_created_by_role ? ` · ${row.document_created_by_role}` : ''}</span><span className="mt-1 block text-xs text-gray-400">انجام‌دهنده گردش: {row.created_by_display ?? 'سیستم'}{row.created_by_role ? ` · ${row.created_by_role}` : ''}</span></td>
                  </tr>)}
                  {!loading && (movementData?.results.length ?? 0) === 0 && <tr><td colSpan={9} className="p-8 text-center text-gray-500">گردشی برای نمایش پیدا نشد.</td></tr>}
                </tbody>
              </table>
            </div>
          )}

          <div className="mt-5 flex items-center justify-between">
            <button disabled={!hasPrevious || loading} onClick={() => setPage(value => Math.max(1, value - 1))} className="rounded-lg border px-4 py-2 text-sm disabled:opacity-40">قبلی</button>
            <span className="text-sm text-gray-500">صفحه {number(page)}</span>
            <button disabled={!hasNext || loading} onClick={() => setPage(value => value + 1)} className="rounded-lg border px-4 py-2 text-sm disabled:opacity-40">بعدی</button>
          </div>
        </section>
      </div>
    </main>
  );
}
