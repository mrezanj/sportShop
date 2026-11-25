'use client';

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/context/AuthContext';

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const inputClass = 'w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-pink-500';
const number = (value: number | string) => Number(value).toLocaleString('fa-IR');
const date = (value: string | null) => value ? new Date(value).toLocaleString('fa-IR') : '—';

type Tab = 'returns' | 'refunds' | 'discrepancies';
type ReturnItem = { order_item_id: number; quantity: number };
type ReturnRequest = {
  id: number; order_id: number; reason: string; status: string;
  status_display: string; staff_note: string; items: ReturnItem[];
  created_at: string; updated_at: string;
};
type RefundHistory = {
  old_status: string; new_status: string; provider_reference: string;
  note: string; created_at: string;
};
type Refund = {
  id: number; order_number: string; return_request_id: number; payment_id: number;
  amount: string; status: string; provider_reference: string;
  provider_response: Record<string, unknown>; idempotency_key: string;
  created_at: string; completed_at: string | null; history: RefundHistory[];
};
type Discrepancy = {
  id: number; order_number: string; status: string; reason: string;
  resolution: string; previous_order_status: string;
  created_at: string; resolved_at: string | null;
};

const returnLabels: Record<string, string> = {
  requested: 'درخواست‌شده', approved: 'تأییدشده', rejected: 'ردشده',
  received: 'دریافت و بررسی‌شده', closed: 'بسته‌شده',
};
const refundLabels: Record<string, string> = {
  requested: 'درخواست‌شده', approved: 'تأییدشده', processing: 'در حال انجام',
  succeeded: 'انجام‌شده', failed: 'ناموفق', rejected: 'ردشده',
};
const discrepancyLabels: Record<string, string> = { open: 'در حال بررسی', resolved: 'رسیدگی‌شده' };

async function api<T>(token: string, path: string, method = 'GET', payload?: unknown): Promise<T> {
  const response = await fetch(`${API_URL}/${path}`, {
    method,
    headers: {
      Authorization: `Token ${token}`,
      ...(payload !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(payload !== undefined ? { body: JSON.stringify(payload) } : {}),
    cache: 'no-store',
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = data?.detail || data?.error || 'درخواست با خطا مواجه شد.';
    throw new Error(message);
  }
  return data as T;
}

export default function ReturnsRefundsAdminPage() {
  const { token, user, loading: authLoading } = useAuth();
  const [tab, setTab] = useState<Tab>('returns');
  const [returns, setReturns] = useState<ReturnRequest[]>([]);
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [discrepancies, setDiscrepancies] = useState<Discrepancy[]>([]);
  const [errors, setErrors] = useState<Partial<Record<Tab, string>>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [refundAmounts, setRefundAmounts] = useState<Record<number, string>>({});
  const [providerRefs, setProviderRefs] = useState<Record<number, string>>({});
  const [providerEvidence, setProviderEvidence] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    if (!token) return;
    const results = await Promise.allSettled([
      api<ReturnRequest[]>(token, 'orders/returns/'),
      api<Refund[]>(token, 'payments/refunds/'),
      api<Discrepancy[]>(token, 'orders/discrepancies/'),
    ]);
    const nextErrors: Partial<Record<Tab, string>> = {};
    if (results[0].status === 'fulfilled') setReturns(results[0].value);
    else nextErrors.returns = results[0].reason instanceof Error ? results[0].reason.message : 'دریافت مرجوعی‌ها ناموفق بود.';
    if (results[1].status === 'fulfilled') setRefunds(results[1].value);
    else nextErrors.refunds = results[1].reason instanceof Error ? results[1].reason.message : 'دریافت بازپرداخت‌ها ناموفق بود.';
    if (results[2].status === 'fulfilled') setDiscrepancies(results[2].value);
    else nextErrors.discrepancies = results[2].reason instanceof Error ? results[2].reason.message : 'دریافت مغایرت‌ها ناموفق بود.';
    setErrors(nextErrors);
  }, [token]);

  useEffect(() => {
    if (token && user?.is_employee) void load();
  }, [token, user, load]);

  const run = async (key: string, action: () => Promise<unknown>, message: string) => {
    setBusy(key);
    setNotice('');
    try {
      await action();
      setNotice(message);
      await load();
    } catch (error) {
      setErrors((current) => ({ ...current, [tab]: error instanceof Error ? error.message : 'عملیات انجام نشد.' }));
    } finally {
      setBusy(null);
    }
  };

  const reviewReturn = (item: ReturnRequest, decision: 'approved' | 'rejected') => {
    const note = notes[`return-${item.id}`] || '';
    void run(`return-${item.id}`, () => api(token!, `orders/returns/${item.id}/review/`, 'POST', { decision, note }), decision === 'approved' ? 'درخواست مرجوعی تأیید شد.' : 'درخواست مرجوعی رد شد.');
  };

  const receiveReturn = (item: ReturnRequest) => {
    const note = notes[`return-${item.id}`] || '';
    void run(`receive-${item.id}`, () => api(token!, `orders/returns/${item.id}/received/`, 'POST', { note }), 'دریافت و بررسی کالای مرجوعی ثبت شد.');
  };

  const createRefund = (item: ReturnRequest) => {
    const amount = refundAmounts[item.id];
    if (!amount || !Number.isInteger(Number(amount)) || Number(amount) <= 0) {
      setErrors((current) => ({ ...current, refunds: 'مبلغ بازپرداخت باید عدد صحیح مثبت و به تومان باشد.' }));
      setTab('refunds');
      return;
    }
    void run(`create-refund-${item.id}`, () => api(token!, 'payments/refunds/', 'POST', {
      return_request_id: item.id, amount, idempotency_key: crypto.randomUUID(),
    }), 'درخواست بازپرداخت ایجاد شد. این مرحله هنوز وجهی را به مشتری منتقل نمی‌کند.');
  };

  const transitionRefund = (item: Refund, decision: string) => {
    const rawEvidence = providerEvidence[item.id] || '';
    let evidence: Record<string, unknown> = {};
    if (rawEvidence.trim()) {
      try { evidence = JSON.parse(rawEvidence) as Record<string, unknown>; }
      catch { setErrors((current) => ({ ...current, refunds: 'مستند ارائه‌دهنده باید JSON معتبر باشد.' })); return; }
    }
    const note = notes[`refund-${item.id}`] || '';
    void run(`refund-${item.id}`, () => api(token!, `payments/refunds/${item.id}/transition/`, 'POST', {
      decision, provider_reference: providerRefs[item.id] || '', provider_response: evidence, note,
    }), 'وضعیت بازپرداخت به‌روزرسانی شد.');
  };

  const resolveDiscrepancy = (item: Discrepancy) => {
    const resolution = notes[`case-${item.id}`] || '';
    if (!resolution.trim()) {
      setErrors((current) => ({ ...current, discrepancies: 'شرح نتیجه رسیدگی الزامی است.' }));
      return;
    }
    void run(`case-${item.id}`, () => api(token!, `orders/discrepancies/${item.id}/resolve/`, 'POST', { resolution }), 'مغایرت رسیدگی و وضعیت قبلی سفارش بازیابی شد.');
  };

  if (authLoading) return <main className="grid min-h-[60vh] place-items-center">در حال بررسی دسترسی...</main>;
  if (!user || !token) return <main className="container mx-auto px-4 py-16 text-center">برای ورود به پنل عملیاتی ابتدا وارد حساب کاربری شوید.</main>;
  if (!user.is_employee) return <main className="container mx-auto px-4 py-16 text-center text-amber-800">این بخش فقط برای کاربران داخلی فروشگاه است.</main>;

  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: 'returns', label: 'درخواست‌های مرجوعی', count: returns.length },
    { id: 'refunds', label: 'بازپرداخت‌ها', count: refunds.length },
    { id: 'discrepancies', label: 'مغایرت سفارش‌ها', count: discrepancies.length },
  ];

  return (
    <main className="min-h-screen bg-page py-8" dir="rtl">
      <div className="container mx-auto max-w-7xl space-y-6 px-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="section-label">مدیریت فروشگاه</p>
            <h1 className="text-3xl font-bold text-pink-950">مرجوعی، بازپرداخت و مغایرت سفارش</h1>
            <p className="mt-2 text-sm text-gray-600">گردش کار عملیاتی با کنترل مجوزهای مستقل در Backend</p>
          </div>
          <nav className="flex flex-wrap gap-2">
            <a href="/admin/inventory" className="rounded-xl border border-pink-200 bg-white px-4 py-2.5 text-sm font-bold text-pink-900">انبار</a>
            <a href="/admin/pricing" className="rounded-xl border border-pink-200 bg-white px-4 py-2.5 text-sm font-bold text-pink-900">قیمت‌گذاری</a>
            <button onClick={() => void load()} className="rounded-xl bg-pink-800 px-4 py-2.5 text-sm font-bold text-white">به‌روزرسانی</button>
          </nav>
        </header>

        <section className="grid gap-3 sm:grid-cols-3">
          <Metric label="درخواست مرجوعی باز" value={returns.filter((row) => ['requested', 'approved', 'received'].includes(row.status)).length} />
          <Metric label="بازپرداخت نهایی‌نشده" value={refunds.filter((row) => !['succeeded', 'failed', 'rejected'].includes(row.status)).length} />
          <Metric label="مغایرت باز" value={discrepancies.filter((row) => row.status === 'open').length} />
        </section>

        {notice && <div role="status" className="rounded-xl border border-pink-200 bg-white p-3 text-sm text-pink-900">{notice}</div>}
        <div className="flex flex-wrap gap-2 border-b border-pink-100 pb-3">
          {tabs.map((item) => <button key={item.id} onClick={() => setTab(item.id)} className={`rounded-xl px-4 py-2.5 text-sm font-bold ${tab === item.id ? 'bg-pink-800 text-white' : 'border border-pink-100 bg-white text-pink-900'}`}>{item.label} <span className="mr-1 opacity-75">({number(item.count)})</span></button>)}
        </div>

        {errors[tab] && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{errors[tab]}</div>}

        {tab === 'returns' && <section className="space-y-3">
          {returns.map((item) => <article key={item.id} className="rounded-2xl border border-pink-100 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><h2 className="text-lg font-bold text-gray-900">درخواست #{number(item.id)} · سفارش داخلی #{number(item.order_id)}</h2><p className="mt-1 text-xs text-gray-500">ثبت: {date(item.created_at)}</p></div>
              <Status status={item.status} label={item.status_display || returnLabels[item.status] || item.status} />
            </div>
            <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-gray-700">{item.reason}</p>
            <div className="mt-3 flex flex-wrap gap-2">{item.items.map((row) => <span key={row.order_item_id} className="rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-700">قلم سفارش #{number(row.order_item_id)} · تعداد {number(row.quantity)}</span>)}</div>
            {item.staff_note && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">یادداشت قبلی: {item.staff_note}</p>}
            {['requested', 'approved'].includes(item.status) && <div className="mt-4 space-y-3 border-t border-gray-100 pt-4">
              <textarea rows={2} className={inputClass} value={notes[`return-${item.id}`] || ''} onChange={(event) => setNotes((current) => ({ ...current, [`return-${item.id}`]: event.target.value }))} placeholder="یادداشت بررسی (اختیاری)" />
              <div className="flex flex-wrap gap-2">
                {item.status === 'requested' && <>
                  <button disabled={!!busy} onClick={() => reviewReturn(item, 'approved')} className="rounded-xl bg-emerald-700 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">{busy === `return-${item.id}` ? 'در حال ثبت...' : 'تأیید درخواست'}</button>
                  <button disabled={!!busy} onClick={() => reviewReturn(item, 'rejected')} className="rounded-xl border border-red-200 px-4 py-2.5 text-sm font-bold text-red-700 disabled:opacity-50">رد درخواست</button>
                </>}
                {item.status === 'approved' && <button disabled={!!busy} onClick={() => receiveReturn(item)} className="rounded-xl bg-pink-800 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">ثبت دریافت و بررسی کالا</button>}
              </div>
            </div>}
            {item.status === 'received' && <div className="mt-4 grid gap-2 border-t border-gray-100 pt-4 sm:grid-cols-[1fr_auto]">
              <input className={inputClass} inputMode="numeric" value={refundAmounts[item.id] || ''} onChange={(event) => setRefundAmounts((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="مبلغ بازپرداخت به تومان" />
              <button disabled={!!busy} onClick={() => createRefund(item)} className="rounded-xl bg-pink-800 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">ایجاد درخواست بازپرداخت</button>
            </div>}
          </article>)}
          {!returns.length && !errors.returns && <Empty text="درخواستی برای مرجوعی ثبت نشده است." />}
        </section>}

        {tab === 'refunds' && <section className="space-y-3">
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-7 text-amber-900">اتصال خودکار به درگاه بازپرداخت هنوز انجام نشده است. وضعیت «انجام‌شده» فقط پس از انجام واقعی انتقال وجه توسط اپراتور و ثبت شناسه پیگیری و مستند معتبر مجاز است.</div>
          {refunds.map((item) => <article key={item.id} className="rounded-2xl border border-pink-100 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-lg font-bold">بازپرداخت #{number(item.id)} · سفارش {item.order_number}</h2><p className="mt-1 text-sm text-gray-600">مبلغ: <strong>{number(item.amount)} تومان</strong> · درخواست مرجوعی #{number(item.return_request_id)}</p><p className="mt-1 text-xs text-gray-500">ثبت: {date(item.created_at)} · پرداخت مبنا #{number(item.payment_id)}</p></div><Status status={item.status} label={refundLabels[item.status] || item.status} /></div>
            {item.provider_reference && <p className="mt-3 text-sm text-gray-700">شناسه پیگیری: <span dir="ltr" className="font-mono">{item.provider_reference}</span></p>}
            {item.history?.length > 0 && <details className="mt-3 text-sm"><summary className="cursor-pointer font-bold text-pink-900">تاریخچه وضعیت‌ها ({number(item.history.length)})</summary><div className="mt-2 space-y-2 border-r-2 border-pink-100 pr-3">{item.history.map((entry, index) => <div key={index}><p>{refundLabels[entry.old_status] || '—'} ← {refundLabels[entry.new_status] || entry.new_status}</p><p className="text-xs text-gray-500">{date(entry.created_at)} · {entry.note}</p></div>)}</div></details>}
            {!['succeeded', 'failed', 'rejected'].includes(item.status) && <div className="mt-4 space-y-3 border-t border-gray-100 pt-4">
              <textarea rows={2} className={inputClass} value={notes[`refund-${item.id}`] || ''} onChange={(event) => setNotes((current) => ({ ...current, [`refund-${item.id}`]: event.target.value }))} placeholder="یادداشت اقدام" />
              {['approved', 'processing'].includes(item.status) && <>
                <input className={inputClass} value={providerRefs[item.id] || ''} onChange={(event) => setProviderRefs((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="شناسه پیگیری ارائه‌دهنده (برای موفقیت الزامی)" />
                <textarea rows={3} className={inputClass} value={providerEvidence[item.id] || ''} onChange={(event) => setProviderEvidence((current) => ({ ...current, [item.id]: event.target.value }))} placeholder='مستند پاسخ ارائه‌دهنده به صورت JSON؛ نمونه: {"status":"paid","reference":"..."}' dir="ltr" />
              </>}
              <div className="flex flex-wrap gap-2">
                {item.status === 'requested' && <>
                  <ActionButton disabled={!!busy} onClick={() => transitionRefund(item, 'approve')} label="تأیید بازپرداخت" />
                  <button disabled={!!busy} onClick={() => transitionRefund(item, 'reject')} className="rounded-xl border border-red-200 px-4 py-2.5 text-sm font-bold text-red-700 disabled:opacity-50">رد درخواست</button>
                </>}
                {item.status === 'approved' && <ActionButton disabled={!!busy} onClick={() => transitionRefund(item, 'processing')} label="شروع فرایند پرداخت" />}
                {['approved', 'processing'].includes(item.status) && <>
                  <ActionButton disabled={!!busy} onClick={() => transitionRefund(item, 'succeeded')} label="ثبت انتقال وجه موفق" />
                  <button disabled={!!busy} onClick={() => transitionRefund(item, 'failed')} className="rounded-xl border border-red-200 px-4 py-2.5 text-sm font-bold text-red-700 disabled:opacity-50">ثبت ناموفق بودن انتقال</button>
                </>}
              </div>
            </div>}
          </article>)}
          {!refunds.length && !errors.refunds && <Empty text="درخواستی برای بازپرداخت وجود ندارد." />}
        </section>}

        {tab === 'discrepancies' && <section className="space-y-3">
          {discrepancies.map((item) => <article key={item.id} className="rounded-2xl border border-pink-100 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-lg font-bold">پرونده #{number(item.id)} · سفارش {item.order_number}</h2><p className="mt-1 text-xs text-gray-500">ثبت: {date(item.created_at)} · وضعیت قبلی سفارش: {item.previous_order_status}</p></div><Status status={item.status} label={discrepancyLabels[item.status] || item.status} /></div>
            <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-gray-700">{item.reason}</p>
            {item.resolution && <p className="mt-3 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">نتیجه: {item.resolution}</p>}
            {item.status === 'open' && <div className="mt-4 space-y-2 border-t border-gray-100 pt-4"><textarea rows={2} className={inputClass} value={notes[`case-${item.id}`] || ''} onChange={(event) => setNotes((current) => ({ ...current, [`case-${item.id}`]: event.target.value }))} placeholder="شرح نتیجه رسیدگی؛ الزامی" /><button disabled={!!busy} onClick={() => resolveDiscrepancy(item)} className="rounded-xl bg-pink-800 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">ثبت نتیجه و رفع توقف سفارش</button></div>}
          </article>)}
          {!discrepancies.length && !errors.discrepancies && <Empty text="پرونده مغایرتی ثبت نشده است." />}
        </section>}
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-2xl border border-pink-100 bg-white p-4 shadow-sm"><p className="text-xs text-gray-500">{label}</p><p className="mt-2 text-3xl font-extrabold text-pink-950">{number(value)}</p></div>;
}
function Status({ status, label }: { status: string; label: string }) {
  const color = status === 'succeeded' || status === 'resolved' || status === 'received' ? 'bg-emerald-50 text-emerald-800' : status === 'failed' || status === 'rejected' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-800';
  return <span className={`inline-flex rounded-full px-3 py-1 text-xs font-bold ${color}`}>{label}</span>;
}
function Empty({ text }: { text: string }) {
  return <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-10 text-center text-sm text-gray-500">{text}</div>;
}
function ActionButton({ disabled, onClick, label }: { disabled: boolean; onClick: () => void; label: string }) {
  return <button disabled={disabled} onClick={onClick} className="rounded-xl bg-pink-800 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">{label}</button>;
}
