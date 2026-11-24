'use client';

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { useAuth } from '@/context/AuthContext';
import {
  addInventoryDocumentItem,
  approveInventoryDocument,
  createInventoryDocument,
  fetchInventoryDocumentDetail,
  fetchInventoryDocumentHistory,
  fetchInventoryDocuments,
  fetchInventoryLowStock,
  fetchInventorySummary,
  fetchInventoryThresholds,
  rejectInventoryDocument,
  removeInventoryDocumentItem,
  reviewInventoryDocument,
  submitInventoryDocument,
  updateInventoryThreshold,
  type InventoryDocumentDetail,
  type InventoryDocumentLog,
  type InventoryDocumentRow,
  type InventoryStockRow,
  type InventorySummary,
} from '@/lib/api';

const STATUS_LABELS: Record<string, string> = {
  draft: 'پیش‌نویس',
  pending_review: 'در انتظار بررسی حسابدار',
  pending_approval: 'در انتظار تأیید مدیر',
  approved: 'تأییدشده',
  rejected: 'ردشده',
  cancelled: 'لغوشده',
};
const TYPE_LABELS: Record<string, string> = {
  inbound: 'ورود کالا', outbound: 'خروج کالا', purchase: 'خرید',
  return: 'مرجوعی', waste: 'ضایعات', adjustment: 'اصلاح موجودی',
};
const ACTION_LABELS: Record<string, string> = {
  created: 'ایجاد سند', submitted: 'ارسال برای بررسی', reviewed: 'بررسی حسابدار',
  approved: 'تأیید نهایی', rejected: 'رد سند', cancelled: 'لغو سند',
};
const number = (value: number) => new Intl.NumberFormat('fa-IR').format(value);
const date = (value: string) => new Date(value).toLocaleString('fa-IR', {
  year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
});
const inputClass = 'w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-pink-500';

export default function InventoryDashboardPage() {
  const { token, user, loading: authLoading } = useAuth();
  const [summary, setSummary] = useState<InventorySummary | null>(null);
  const [lowStock, setLowStock] = useState<InventoryStockRow[]>([]);
  const [thresholds, setThresholds] = useState<InventoryStockRow[]>([]);
  const [documents, setDocuments] = useState<InventoryDocumentRow[]>([]);
  const [docCount, setDocCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [type, setType] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [selected, setSelected] = useState<InventoryDocumentDetail | null>(null);
  const [history, setHistory] = useState<InventoryDocumentLog[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [thresholdDrafts, setThresholdDrafts] = useState<Record<number, string>>({});
  const [savingThreshold, setSavingThreshold] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [docForm, setDocForm] = useState({
    document_number: '', document_type: 'inbound', reference: '', reason: '', notes: '',
  });
  const [itemForm, setItemForm] = useState({
    variant: '', quantity: '1', direction: 'inbound', new_batch_number: '',
    new_batch_expiration_date: '', unit_cost: '', reason: '',
  });
  const [workflowNote, setWorkflowNote] = useState('');

  const loadDashboard = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const [summaryData, lowData, thresholdData, docsData] = await Promise.all([
        fetchInventorySummary(token),
        fetchInventoryLowStock(token),
        fetchInventoryThresholds(token),
        fetchInventoryDocuments(token, { page, status, type, search }),
      ]);
      setSummary(summaryData);
      setLowStock(lowData.results);
      setThresholds(thresholdData);
      setDocuments(docsData.results);
      setDocCount(docsData.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'خطا در دریافت اطلاعات داشبورد.');
    } finally {
      setLoading(false);
    }
  }, [token, page, status, type, search]);

  useEffect(() => {
    if (token) void loadDashboard();
  }, [token, loadDashboard]);

  const openDocument = async (id: number) => {
    if (!token) return;
    setDetailLoading(true);
    setSelected(null);
    setHistory([]);
    setWorkflowNote('');
    try {
      const [detail, events] = await Promise.all([
        fetchInventoryDocumentDetail(token, id),
        fetchInventoryDocumentHistory(token, id),
      ]);
      setSelected(detail);
      setHistory(events);
      setItemForm({
        variant: '', quantity: '1',
        direction: ['outbound', 'waste'].includes(detail.document_type) ? 'outbound' : 'inbound',
        new_batch_number: '', new_batch_expiration_date: '', unit_cost: '', reason: '',
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'خطا در دریافت جزئیات سند.');
    } finally {
      setDetailLoading(false);
    }
  };

  const refreshSelected = async () => {
    if (!selected) return;
    await openDocument(selected.id);
    await loadDashboard();
  };

  const saveThreshold = async (row: InventoryStockRow) => {
    if (!token) return;
    const value = Number(thresholdDrafts[row.variant_id] ?? row.minimum_quantity);
    if (!Number.isInteger(value) || value < 0) {
      setNotice('حداقل موجودی باید عدد صحیح و غیرمنفی باشد.');
      return;
    }
    setSavingThreshold(row.variant_id);
    setNotice('');
    try {
      await updateInventoryThreshold(token, row.variant_id, value);
      setThresholdDrafts(prev => ({ ...prev, [row.variant_id]: String(value) }));
      setNotice(\`حداقل موجودی \${row.sku} ذخیره شد.\`);
      await loadDashboard();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'ذخیره حداقل موجودی انجام نشد.');
    } finally {
      setSavingThreshold(null);
    }
  };

  const createDocument = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) return;
    setSaving(true);
    setNotice('');
    try {
      const result = await createInventoryDocument(token, docForm);
      setCreating(false);
      setDocForm({ document_number: '', document_type: 'inbound', reference: '', reason: '', notes: '' });
      await loadDashboard();
      await openDocument(result.id);
      setNotice('سند پیش‌نویس ایجاد شد. اکنون اقلام آن را ثبت کنید.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'ایجاد سند انجام نشد.');
    } finally {
      setSaving(false);
    }
  };

  const addItem = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token || !selected) return;
    const quantity = Number(itemForm.quantity);
    const variant = Number(itemForm.variant);
    if (!Number.isInteger(quantity) || quantity <= 0 || !variant) {
      setNotice('SKU و تعداد معتبر را انتخاب کنید.');
      return;
    }
    const inbound = itemForm.direction === 'inbound';
    if (inbound && !itemForm.new_batch_number.trim()) {
      setNotice('برای کالای ورودی، شماره بچ جدید الزامی است.');
      return;
    }
    setSaving(true);
    setNotice('');
    try {
      await addInventoryDocumentItem(token, selected.id, {
        variant,
        quantity,
        direction: itemForm.direction as 'inbound' | 'outbound',
        ...(inbound ? {
          new_batch_number: itemForm.new_batch_number.trim(),
          new_batch_expiration_date: itemForm.new_batch_expiration_date || null,
        } : {}),
        unit_cost: itemForm.unit_cost ? Number(itemForm.unit_cost) : null,
        reason: itemForm.reason,
      });
      setItemForm(prev => ({
        ...prev, variant: '', quantity: '1', new_batch_number: '',
        new_batch_expiration_date: '', unit_cost: '', reason: '',
      }));
      await refreshSelected();
      setNotice('ردیف به پیش‌نویس اضافه شد.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'ثبت ردیف انجام نشد.');
    } finally {
      setSaving(false);
    }
  };

  const removeItem = async (itemId: number) => {
    if (!token || !selected) return;
    setSaving(true);
    setNotice('');
    try {
      await removeInventoryDocumentItem(token, selected.id, itemId);
      await refreshSelected();
      setNotice('ردیف از پیش‌نویس حذف شد.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'حذف ردیف انجام نشد.');
    } finally {
      setSaving(false);
    }
  };

  const runWorkflow = async (action: 'submit' | 'review' | 'approve' | 'reject') => {
    if (!token || !selected) return;
    if (action === 'reject' && !workflowNote.trim()) {
      setNotice('برای رد سند، ثبت دلیل الزامی است.');
      return;
    }
    if (!window.confirm(
      action === 'submit' ? 'سند برای بررسی حسابدار ارسال شود؟' :
      action === 'review' ? 'بررسی حسابدار ثبت و سند به مدیر ارجاع شود؟' :
      action === 'approve' ? 'تأیید نهایی انجام شود و گردش موجودی ثبت گردد؟' :
      'سند رد شود؟'
    )) return;
    setSaving(true);
    setNotice('');
    try {
      if (action === 'submit') await submitInventoryDocument(token, selected.id);
      if (action === 'review') await reviewInventoryDocument(token, selected.id, workflowNote);
      if (action === 'approve') await approveInventoryDocument(token, selected.id, workflowNote);
      if (action === 'reject') await rejectInventoryDocument(token, selected.id, workflowNote);
      await refreshSelected();
      setNotice('اقدام با موفقیت ثبت شد.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'تغییر وضعیت سند انجام نشد.');
    } finally {
      setSaving(false);
    }
  };

  const canManageThreshold = summary?.can_manage_threshold ?? false;
  const canEditDraft = !!selected && selected.status === 'draft' &&
    selected.created_by_id === user?.id && !!summary?.can_create_document;
  const canReview = !!selected && selected.status === 'pending_review' &&
    !!summary?.can_review_document && selected.created_by_id !== user?.id;
  const canApprove = !!selected && selected.status === 'pending_approval' &&
    !!summary?.can_approve_document && selected.created_by_id !== user?.id &&
    selected.reviewed_by_id !== user?.id;
  const canReject = canReview || (!!selected && selected.status === 'pending_approval' &&
    !!summary?.can_approve_document && selected.created_by_id !== user?.id &&
    selected.reviewed_by_id !== user?.id);
  const fixedDirection = selected && selected.document_type !== 'adjustment';
  const itemDirection = selected && ['outbound', 'waste'].includes(selected.document_type)
    ? 'outbound' : 'inbound';

  if (authLoading || loading && !summary && !error) {
    return <div className="min-h-[60vh] grid place-items-center text-pink-900">در حال بارگذاری داشبورد انبار...</div>;
  }
  if (!user || !token) {
    return <main className="container mx-auto px-4 py-16"><div className="max-w-xl mx-auto rounded-2xl border border-pink-100 bg-white p-8 text-center shadow-sm"><h1 className="text-2xl mb-3">ورود به پنل انبار</h1><p className="text-gray-600">برای مشاهده اطلاعات انبار ابتدا وارد حساب کاربری شوید.</p><a href="/login" className="inline-flex mt-5 rounded-xl bg-pink-800 px-6 py-3 font-bold text-white">ورود به حساب</a></div></main>;
  }
  if (!user.is_staff) {
    return <main className="container mx-auto px-4 py-16"><div className="max-w-xl mx-auto rounded-2xl border border-amber-200 bg-amber-50 p-8 text-center"><h1 className="text-2xl text-amber-900 mb-3">دسترسی محدود است</h1><p className="text-amber-800">این بخش فقط برای کاربران داخلی فروشگاه در دسترس است.</p></div></main>;
  }

  return (
    <main className="min-h-screen bg-page py-8 sm:py-10">
      <div className="container mx-auto max-w-7xl px-4 space-y-7">
        <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div><p className="section-label">مدیریت عملیات فروشگاه</p><h1 className="text-3xl sm:text-4xl">داشبورد انبار</h1><p className="mt-2 text-sm text-gray-500">نمای موجودی، ثبت اسناد و گردش تأیید حسابدار و مدیر داخلی</p></div>
          <div className="flex flex-wrap gap-2">
            {summary?.can_create_document && <button onClick={() => setCreating(true)} className="rounded-xl bg-pink-800 px-4 py-2.5 text-sm font-bold text-white hover:bg-pink-900">ایجاد سند جدید</button>}
            <button onClick={() => void loadDashboard()} className="rounded-xl border border-pink-200 bg-white px-4 py-2.5 text-sm font-bold text-pink-900 hover:bg-pink-50">به‌روزرسانی اطلاعات</button>
          </div>
        </header>
        {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>}
        {notice && <div role="status" className="rounded-xl border border-pink-200 bg-white px-4 py-3 text-sm text-pink-900">{notice}</div>}

        {summary && <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Metric title="تعداد SKU فعال" value={summary.sku_count} detail="تنوع کالای فعال" />
          <Metric title="موجودی فیزیکی" value={summary.physical_quantity} detail="جمع تعداد در انبار" />
          <Metric title="موجودی رزروشده" value={summary.reserved_quantity} detail="اختصاص‌یافته به سفارش‌ها" />
          <Metric title="موجودی قابل فروش" value={summary.available_quantity} detail="پس از کسر رزروها" />
          <Metric title="کالاهای زیر حداقل" value={summary.low_stock_count} detail="نیازمند بررسی تأمین" warning />
          <Metric title="در انتظار بررسی" value={summary.pending_review_count} detail="مرحله حسابدار" />
          <Metric title="در انتظار تأیید" value={summary.pending_approval_count} detail="مرحله مدیر داخلی" />
          <Metric title="هشدار کمبود" value={lowStock.length} detail="SKU دارای حداقل تعریف‌شده" warning />
        </section>}

        <section className="rounded-2xl border border-pink-100 bg-white p-4 shadow-sm sm:p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2"><div><h2 className="text-xl">هشدار کمبود موجودی</h2><p className="text-xs text-gray-500 mt-1">موجودی قابل فروش کمتر از حداقل تعیین‌شده</p></div><span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-800">{number(lowStock.length)} کالا</span></div>
          <StockTable rows={lowStock} />
        </section>

        <section className="rounded-2xl border border-pink-100 bg-white p-4 shadow-sm sm:p-6">
          <div className="mb-4"><h2 className="text-xl">مدیریت حداقل موجودی SKU</h2><p className="mt-1 text-xs text-gray-500">تغییر حداقل موجودی با مجوز مدیر انجام می‌شود.</p></div>
          <div className="overflow-x-auto"><table className="w-full min-w-[720px] text-sm"><thead><tr className="border-b border-gray-100 text-right text-gray-500"><th className="p-3">SKU / محصول</th><th className="p-3">قابل فروش</th><th className="p-3">حداقل فعلی</th><th className="p-3">حداقل جدید</th><th className="p-3">عملیات</th></tr></thead>
            <tbody>{thresholds.slice(0, 30).map(row => <tr key={row.variant_id} className="border-b border-gray-50 last:border-0"><td className="p-3"><strong className="block text-gray-800">{row.sku}</strong><span className="text-xs text-gray-500">{row.product_name}</span></td><td className="p-3 tabular-nums">{number(row.available)}</td><td className="p-3 tabular-nums">{number(row.minimum_quantity)}</td><td className="p-3"><input aria-label={\`حداقل موجودی \${row.sku}\`} inputMode="numeric" value={thresholdDrafts[row.variant_id] ?? String(row.minimum_quantity)} onChange={e => setThresholdDrafts(prev => ({...prev, [row.variant_id]: e.target.value}))} className="w-24 rounded-lg border border-gray-200 px-3 py-2 outline-none focus:border-pink-500" /></td><td className="p-3"><button disabled={!canManageThreshold || savingThreshold === row.variant_id} onClick={() => void saveThreshold(row)} className="rounded-lg bg-pink-800 px-3 py-2 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-40">{savingThreshold === row.variant_id ? 'در حال ذخیره' : 'ذخیره'}</button></td></tr>)}</tbody>
          </table></div>
          {!canManageThreshold && <p className="mt-3 text-xs text-amber-700">تغییر حداقل موجودی فقط برای مدیر دارای مجوز تأیید نهایی فعال است.</p>}
          {thresholds.length > 30 && <p className="mt-3 text-xs text-gray-500">در این نما ۳۰ SKU نخست نمایش داده می‌شود.</p>}
        </section>

        <section className="rounded-2xl border border-pink-100 bg-white p-4 shadow-sm sm:p-6">
          <div className="mb-4"><h2 className="text-xl">اسناد انبار</h2><p className="mt-1 text-xs text-gray-500">ایجاد پیش‌نویس، افزودن اقلام و گردش بررسی و تأیید</p></div>
          <div className="mb-4 grid gap-2 sm:grid-cols-4">
            <input value={search} onChange={e => {setSearch(e.target.value);setPage(1);}} placeholder="جست‌وجوی شماره سند یا توضیحات" className={inputClass + ' sm:col-span-2'} />
            <select value={status} onChange={e => {setStatus(e.target.value);setPage(1);}} className={inputClass}><option value="">همه وضعیت‌ها</option>{Object.entries(STATUS_LABELS).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select>
            <select value={type} onChange={e => {setType(e.target.value);setPage(1);}} className={inputClass}><option value="">همه انواع سند</option>{Object.entries(TYPE_LABELS).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select>
          </div>
          <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-sm"><thead><tr className="border-b border-gray-100 text-right text-gray-500"><th className="p-3">شماره سند</th><th className="p-3">نوع</th><th className="p-3">وضعیت</th><th className="p-3">ثبت‌کننده</th><th className="p-3">تعداد ردیف</th><th className="p-3">تاریخ</th><th className="p-3">جزئیات</th></tr></thead>
            <tbody>{documents.map(doc=><tr key={doc.id} className="border-b border-gray-50 last:border-0"><td className="p-3 font-bold text-gray-800">{doc.document_number}</td><td className="p-3">{TYPE_LABELS[doc.document_type] ?? doc.document_type}</td><td className="p-3"><StatusPill status={doc.status} /></td><td className="p-3">{doc.created_by_username ?? 'سیستم'}</td><td className="p-3 tabular-nums">{number(doc.item_count)}</td><td className="p-3 whitespace-nowrap">{date(doc.created_at)}</td><td className="p-3"><button onClick={() => void openDocument(doc.id)} className="font-bold text-pink-800 hover:text-pink-950">مشاهده و عملیات</button></td></tr>)}</tbody>
          </table>{!documents.length && <p className="py-8 text-center text-sm text-gray-500">سندی با این مشخصات پیدا نشد.</p>}</div>
          <div className="mt-4 flex items-center justify-between text-sm"><span className="text-gray-500">مجموع {number(docCount)} سند</span><div className="flex gap-2"><button disabled={page<=1} onClick={()=>setPage(p=>p-1)} className="rounded-lg border px-3 py-2 disabled:opacity-40">قبلی</button><span className="px-2 py-2">صفحه {number(page)}</span><button disabled={documents.length===0 || page*20>=docCount} onClick={()=>setPage(p=>p+1)} className="rounded-lg border px-3 py-2 disabled:opacity-40">بعدی</button></div></div>
        </section>
      </div>

      {creating && <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-3 sm:p-8" onClick={()=>setCreating(false)}><div role="dialog" aria-modal="true" aria-label="ایجاد سند انبار" className="my-4 w-full max-w-2xl rounded-2xl bg-white p-5 shadow-2xl sm:p-7" onClick={e=>e.stopPropagation()}>
        <div className="mb-5 flex items-center justify-between"><h2 className="text-xl font-bold">ایجاد سند پیش‌نویس</h2><button onClick={()=>setCreating(false)} className="rounded-lg border px-3 py-2 text-sm">بستن</button></div>
        <form onSubmit={createDocument} className="grid gap-4 sm:grid-cols-2">
          <Field label="شماره سند *"><input required maxLength={50} value={docForm.document_number} onChange={e=>setDocForm(p=>({...p,document_number:e.target.value}))} className={inputClass} /></Field>
          <Field label="نوع سند"><select value={docForm.document_type} onChange={e=>setDocForm(p=>({...p,document_type:e.target.value}))} className={inputClass}>{Object.entries(TYPE_LABELS).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></Field>
          <Field label="شماره مرجع"><input value={docForm.reference} onChange={e=>setDocForm(p=>({...p,reference:e.target.value}))} className={inputClass} /></Field>
          <Field label="دلیل عملیات"><input value={docForm.reason} onChange={e=>setDocForm(p=>({...p,reason:e.target.value}))} className={inputClass} /></Field>
          <div className="sm:col-span-2"><Field label="توضیحات"><textarea value={docForm.notes} onChange={e=>setDocForm(p=>({...p,notes:e.target.value}))} className={inputClass} rows={3} /></Field></div>
          <div className="sm:col-span-2 flex justify-end gap-2"><button type="button" onClick={()=>setCreating(false)} className="rounded-xl border px-4 py-2.5 text-sm">انصراف</button><button disabled={saving} className="rounded-xl bg-pink-800 px-5 py-2.5 text-sm font-bold text-white disabled:opacity-50">{saving?'در حال ثبت...':'ایجاد پیش‌نویس'}</button></div>
        </form>
      </div></div>}

      {(detailLoading || selected) && <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-3 sm:p-8" onClick={()=>{setSelected(null);setHistory([]);}}><div role="dialog" aria-modal="true" aria-label="جزئیات و عملیات سند انبار" className="my-4 w-full max-w-5xl rounded-2xl bg-white p-5 shadow-2xl sm:p-7" onClick={e=>e.stopPropagation()}>
        {detailLoading ? <p className="py-12 text-center">در حال دریافت جزئیات...</p> : selected && <>
          <div className="flex items-start justify-between gap-3"><div><p className="section-label">جزئیات و گردش سند انبار</p><h2 className="text-2xl font-bold">{selected.document_number}</h2><p className="mt-1 text-sm text-gray-500">{TYPE_LABELS[selected.document_type] ?? selected.document_type} · {date(selected.created_at)}</p></div><button onClick={()=>{setSelected(null);setHistory([]);}} className="rounded-lg border px-3 py-2 text-sm">بستن</button></div>
          <div className="mt-5 flex flex-wrap items-center gap-3"><StatusPill status={selected.status}/><span className="text-sm text-gray-600">ثبت‌کننده: {selected.created_by_username ?? 'سیستم'}</span><span className="text-sm text-gray-600">تعداد ردیف: {number(selected.items.length)}</span></div>
          {canEditDraft && <section className="mt-6 rounded-xl border border-pink-100 bg-pink-50/40 p-4"><h3 className="font-bold text-pink-950">افزودن کالا به پیش‌نویس</h3><p className="mt-1 text-xs text-gray-500">برای ورود کالا، شماره بچ جدید ثبت می‌شود؛ خروج کالا با تخصیص خودکار FEFO انجام می‌شود.</p>
            <form onSubmit={addItem} className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="SKU / محصول *"><select required value={itemForm.variant} onChange={e=>setItemForm(p=>({...p,variant:e.target.value}))} className={inputClass}><option value="">انتخاب کالا</option>{thresholds.map(row=><option key={row.variant_id} value={row.variant_id}>{row.sku} — {row.product_name}</option>)}</select></Field>
              <Field label="تعداد *"><input required type="number" min="1" step="1" value={itemForm.quantity} onChange={e=>setItemForm(p=>({...p,quantity:e.target.value}))} className={inputClass} /></Field>
              <Field label="جهت عملیات">{fixedDirection ? <input readOnly value={itemDirection==='inbound'?'ورودی':'خروجی'} className={inputClass+' bg-gray-50'} /> : <select value={itemForm.direction} onChange={e=>setItemForm(p=>({...p,direction:e.target.value}))} className={inputClass}><option value="inbound">ورودی</option><option value="outbound">خروجی</option></select>}</Field>
              {itemForm.direction==='inbound' && <><Field label="شماره بچ جدید *"><input required value={itemForm.new_batch_number} onChange={e=>setItemForm(p=>({...p,new_batch_number:e.target.value}))} className={inputClass} /></Field><Field label="تاریخ انقضا"><input type="date" value={itemForm.new_batch_expiration_date} onChange={e=>setItemForm(p=>({...p,new_batch_expiration_date:e.target.value}))} className={inputClass} /></Field><Field label="بهای واحد (تومان)"><input type="number" min="0" step="1" value={itemForm.unit_cost} onChange={e=>setItemForm(p=>({...p,unit_cost:e.target.value}))} className={inputClass} /></Field></>}
              <Field label="دلیل ردیف"><input value={itemForm.reason} onChange={e=>setItemForm(p=>({...p,reason:e.target.value}))} className={inputClass} /></Field>
              <div className="flex items-end"><button disabled={saving} className="w-full rounded-xl bg-pink-800 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">{saving?'در حال ثبت...':'افزودن ردیف'}</button></div>
            </form>
          </section>}
          <div className="mt-5 overflow-x-auto"><table className="w-full min-w-[680px] text-sm"><thead><tr className="border-b text-right text-gray-500"><th className="p-3">SKU / کالا</th><th className="p-3">بچ</th><th className="p-3">جهت</th><th className="p-3">تعداد</th><th className="p-3">بهای واحد</th><th className="p-3">تاریخ انقضا</th>{canEditDraft&&<th className="p-3">عملیات</th>}</tr></thead>
            <tbody>{selected.items.map(item=><tr key={item.id} className="border-b border-gray-50"><td className="p-3"><strong>{item.sku}</strong><span className="block text-xs text-gray-500">{item.product_name}</span></td><td className="p-3">{item.batch_number ?? '—'}{item.new_batch_number ? \` · \${item.new_batch_number}\` : ''}</td><td className="p-3">{item.direction==='inbound'?'ورودی':'خروجی'}</td><td className="p-3 tabular-nums">{number(item.quantity)}</td><td className="p-3 tabular-nums">{item.unit_cost===null?'—':number(Number(item.unit_cost))}</td><td className="p-3">{item.batch_expiration_date ?? item.new_batch_expiration_date ?? '—'}</td>{canEditDraft&&<td className="p-3"><button disabled={saving} onClick={()=>void removeItem(item.id)} className="font-bold text-red-700 disabled:opacity-40">حذف</button></td>}</tr>)}</tbody>
          </table>{!selected.items.length&&<p className="py-6 text-center text-sm text-gray-500">هنوز کالایی به سند اضافه نشده است.</p>}</div>
          {(canEditDraft || canReview || canApprove || canReject) && <section className="mt-6 rounded-xl border border-gray-200 p-4"><h3 className="font-bold">اقدام روی سند</h3>
            {(canReview || canApprove || canReject) && <div className="mt-3"><label className="mb-1 block text-xs text-gray-600">یادداشت بررسی / دلیل رد</label><textarea rows={2} value={workflowNote} onChange={e=>setWorkflowNote(e.target.value)} className={inputClass} placeholder="برای رد سند، توضیح الزامی است." /></div>}
            <div className="mt-4 flex flex-wrap gap-2">
              {canEditDraft && <button disabled={saving || selected.items.length===0} onClick={()=>void runWorkflow('submit')} className="rounded-xl bg-pink-800 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-40">ارسال برای بررسی حسابدار</button>}
              {canReview && <button disabled={saving} onClick={()=>void runWorkflow('review')} className="rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-40">ثبت بررسی حسابدار</button>}
              {canApprove && <button disabled={saving} onClick={()=>void runWorkflow('approve')} className="rounded-xl bg-emerald-700 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-40">تأیید نهایی و ثبت موجودی</button>}
              {canReject && <button disabled={saving} onClick={()=>void runWorkflow('reject')} className="rounded-xl bg-red-700 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-40">رد سند</button>}
            </div>
          </section>}
          <div className="mt-7"><h3 className="text-lg font-bold">تاریخچه اقدامات</h3><div className="mt-3 space-y-3">{history.map(event=><div key={event.id} className="flex gap-3 border-r-2 border-pink-200 pr-4"><div className="min-w-0"><p className="font-bold text-gray-800">{ACTION_LABELS[event.action] ?? event.action}</p><p className="text-xs text-gray-500">{event.actor_username ?? event.actor_type} · {date(event.created_at)}</p>{event.note && <p className="mt-1 text-sm text-gray-600">{event.note}</p>}</div></div>)}{!history.length && <p className="text-sm text-gray-500">برای این سند هنوز رویداد تاریخچه‌ای ثبت نشده است.</p>}</div></div>
        </>}
      </div></div>}
    </main>
  );
}

function Field({label,children}:{label:string;children:ReactNode}) {
  return <label className="block text-sm"><span className="mb-1.5 block text-xs font-semibold text-gray-600">{label}</span>{children}</label>;
}
function Metric({title,value,detail,warning=false}:{title:string;value:number;detail:string;warning?:boolean}) {
  return <div className={\`rounded-2xl border bg-white p-4 shadow-sm sm:p-5 \${warning?'border-amber-200':'border-pink-100'}\`}><p className="text-xs font-semibold text-gray-500">{title}</p><p className={\`mt-2 text-3xl font-extrabold tabular-nums \${warning?'text-amber-700':'text-pink-950'}\`}>{number(value)}</p><p className="mt-1 text-[11px] text-gray-400">{detail}</p></div>;
}
function StatusPill({status}:{status:string}) {
  const tone = status==='approved'?'bg-emerald-50 text-emerald-800':status==='rejected'||status==='cancelled'?'bg-red-50 text-red-700':status==='draft'?'bg-gray-100 text-gray-700':'bg-amber-50 text-amber-800';
  return <span className={\`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-bold \${tone}\`}>{STATUS_LABELS[status]??status}</span>;
}
function StockTable({rows}:{rows:InventoryStockRow[]}) {
  return <div className="overflow-x-auto"><table className="w-full min-w-[650px] text-sm"><thead><tr className="border-b border-gray-100 text-right text-gray-500"><th className="p-3">SKU / محصول</th><th className="p-3">فیزیکی</th><th className="p-3">رزروشده</th><th className="p-3">قابل فروش</th><th className="p-3">حداقل</th></tr></thead><tbody>{rows.map(row=><tr key={row.variant_id} className="border-b border-gray-50 last:border-0"><td className="p-3"><strong className="block">{row.sku}</strong><span className="text-xs text-gray-500">{row.product_name}</span></td><td className="p-3 tabular-nums">{number(row.physical)}</td><td className="p-3 tabular-nums">{number(row.reserved)}</td><td className="p-3 font-bold tabular-nums text-amber-700">{number(row.available)}</td><td className="p-3 tabular-nums">{number(row.minimum_quantity)}</td></tr>)}</tbody></table>{!rows.length&&<p className="py-7 text-center text-sm text-emerald-700">در حال حاضر کالایی زیر حداقل موجودی نیست.</p>}</div>;
}
