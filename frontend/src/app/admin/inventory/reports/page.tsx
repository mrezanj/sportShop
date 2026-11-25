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
const dateTimeParts = (value: string) => {
  const parsed = new Date(value);
  return {
    date: parsed.toLocaleDateString('fa-IR'),
    time: parsed.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
  };
};

const movementRowClass = (type: string, index: number) => {
  const tones: Record<string, [string, string]> = {
    inbound: ['bg-emerald-50', 'bg-emerald-100/70'],
    outbound: ['bg-rose-50', 'bg-rose-100/70'],
    return: ['bg-sky-50', 'bg-sky-100/70'],
    waste: ['bg-amber-50', 'bg-amber-100/70'],
    adjustment: ['bg-violet-50', 'bg-violet-100/70'],
    reversal: ['bg-slate-100', 'bg-slate-200/80'],
  };
  const [base, alternate] = tones[type] ?? ['bg-slate-100', 'bg-slate-200/70'];
  return `${index % 2 === 0 ? base : alternate} hover:brightness-[0.98] transition-colors [&>td]:border-b-2 [&>td]:border-white/90`;
};

const movementBadgeClass = (type: string) => {
  const tones: Record<string, string> = {
    inbound: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
    outbound: 'bg-rose-100 text-rose-800 ring-rose-200',
    return: 'bg-sky-100 text-sky-800 ring-sky-200',
    waste: 'bg-amber-100 text-amber-800 ring-amber-200',
    adjustment: 'bg-violet-100 text-violet-800 ring-violet-200',
    reversal: 'bg-slate-200 text-slate-800 ring-slate-300',
  };
  return tones[type] ?? 'bg-slate-200 text-slate-700 ring-slate-300';
};
const inputClass = 'w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-pink-500';

function PersonEntry({ label, name, role }: { label: string; name: string | null; role: string | null }) {
  const isDocumentCreator = label === 'ثبت‌کننده سند';
  return (
    <div className={`min-w-0 rounded-lg border p-2 ${isDocumentCreator ? 'border-sky-200 bg-sky-50' : 'border-amber-200 bg-amber-50'}`}>
      <div className={`text-xs font-bold ${isDocumentCreator ? 'text-sky-800' : 'text-amber-800'}`}>{label}</div>
      <div className="mt-1 break-words font-bold text-gray-900">{name || '—'}</div>
      {role && <div className="mt-1 inline-flex rounded-md bg-white/80 px-2 py-1 text-xs font-medium text-gray-700">نقش: {role}</div>}
    </div>
  );
}

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
        <header className="flex flex-wrap items-end justify-between gap-3 align-middle">
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

        <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4 shadow-sm sm:p-6">
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
          <div className="mb-3 inline-flex rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700">تعداد نتایج: {number(currentCount)}</div>

          {tab === 'batches' ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1050px] border-separate border-spacing-0 text-sm">
                <thead><tr className="bg-slate-200 text-right text-slate-700">
                  <th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold">SKU / کالا</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">شماره بچ</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">وضعیت</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">انقضا</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">فیزیکی</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">رزرو</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">قابل فروش</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">افراد مرتبط</th>
                </tr></thead>
                <tbody>
                  {(batchData?.results ?? []).map((row: InventoryBatchReportRow) => <tr key={row.id} className="bg-slate-100 even:bg-sky-50/80 hover:bg-sky-100 transition-colors [&>td]:border-b-2 [&>td]:border-white">
                    <td className="border-b-2 border-slate-200 p-3 align-middle"><strong>{row.sku}</strong><span className="block text-xs text-gray-500">{row.product_name} · {row.brand_name}</span></td>
                    <td className="border-b-2 border-slate-200 p-3 align-middle font-mono text-slate-700">{row.batch_number}</td>
                    <td className="border-b-2 border-slate-200 p-3 align-middle"><span className={`inline-flex whitespace-nowrap rounded-full px-3 py-1 text-xs font-bold ${row.is_expired ? 'bg-rose-100 text-rose-800' : row.status === 'available' ? 'bg-emerald-100 text-emerald-800' : row.status === 'quarantined' ? 'bg-amber-100 text-amber-800' : 'bg-slate-200 text-slate-700'}`}>{row.is_expired ? 'منقضی' : row.status_display}</span></td>
                    <td className="border-b-2 border-slate-200 p-3 align-middle">{date(row.expiration_date)}</td><td className="border-b-2 border-slate-200 p-3 align-middle tabular-nums">{number(row.physical)}</td><td className="border-b-2 border-slate-200 p-3 align-middle tabular-nums">{number(row.reserved)}</td><td className="border-b-2 border-slate-200 p-3 align-middle tabular-nums font-bold text-slate-900">{number(row.available)}</td>
                    <td className="border-b-2 border-slate-200 p-3 align-middle">
                      <div className="space-y-2">
                        <PersonEntry label="ثبت‌کننده سند" name={row.document_created_by_display} role={row.document_created_by_role} />
                        <div className="border-t border-dashed border-gray-200" />
                        <PersonEntry label="ایجادکننده بچ" name={row.created_by_display} role={row.created_by_role} />
                      </div>
                    </td>
                  </tr>)}
                  {!loading && (batchData?.results.length ?? 0) === 0 && <tr><td colSpan={8} className="border-b border-slate-200 bg-white p-8 text-center text-gray-500">بچی برای نمایش پیدا نشد.</td></tr>}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1250px] border-separate border-spacing-0 text-sm">
                <thead><tr className="bg-slate-200 text-right text-slate-700">
                  <th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">تاریخ</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">SKU</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">بچ</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">نوع گردش</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">تغییر تعداد</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">شماره سند</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">وضعیت سند</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">بهای واحد (تومان)</th><th className="border-b-2 border-slate-300 p-3 text-center align-middle font-bold whitespace-nowrap">افراد مرتبط</th>
                </tr></thead>
                <tbody>
                  {(movementData?.results ?? []).map((row: InventoryMovementReportRow, index: number) => <tr key={row.id} className={movementRowClass(row.movement_type, index)}>
                    <td className="border-b-2 border-white/90 p-3 align-middle whitespace-nowrap"><div className="font-semibold text-slate-800">{dateTimeParts(row.created_at).date}</div><div className="mt-1 text-xs tabular-nums text-slate-500">{dateTimeParts(row.created_at).time}</div></td><td className="border-b-2 border-slate-200 p-3 align-middle">{row.sku}<span className="block text-xs text-gray-500">{row.product_name}</span></td><td className="border-b-2 border-slate-200 p-3 align-middle font-mono">{row.batch_number}</td><td className="border-b-2 border-white/90 p-3 align-middle"><span className={`inline-flex whitespace-nowrap rounded-full px-3 py-1 text-xs font-bold ring-1 ring-inset ${movementBadgeClass(row.movement_type)}`}>{row.movement_type_display}</span></td>
                    <td className={'border-b-2 border-slate-200 p-3 align-middle font-bold tabular-nums ' + (row.quantity_delta > 0 ? 'text-green-700' : 'text-red-700')}>{row.quantity_delta > 0 ? '+' : ''}{number(row.quantity_delta)}</td>
                    <td className="border-b-2 border-slate-200 p-3 align-middle">{row.document_number}<span className="block text-xs text-gray-500">{row.document_type_display}</span></td><td className="border-b-2 border-slate-200 p-3 align-middle">{row.document_status_display}</td><td className="border-b-2 border-slate-200 p-3 align-middle tabular-nums">{row.unit_cost === null ? '—' : number(Number(row.unit_cost))}</td>
                    <td className="border-b-2 border-slate-200 p-3 align-middle">
                      <div className="space-y-3">
                        <PersonEntry label="ثبت‌کننده سند" name={row.document_created_by_display} role={row.document_created_by_role} />
                        <div className="border-t border-dashed border-gray-200" />
                        <PersonEntry label="انجام‌دهنده گردش" name={row.created_by_display ?? 'سیستم'} role={row.created_by_role} />
                      </div>
                    </td>
                  </tr>)}
                  {!loading && (movementData?.results.length ?? 0) === 0 && <tr><td colSpan={9} className="border-b border-slate-200 bg-white p-8 text-center text-gray-500">گردشی برای نمایش پیدا نشد.</td></tr>}
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
