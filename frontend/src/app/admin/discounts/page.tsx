'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useAuth } from '@/context/AuthContext';
import {
  createDiscountCampaign,
  deleteDiscountCampaign,
  fetchDiscountCampaigns,
  updateDiscountCampaign,
  type DiscountCampaign,
  type DiscountCampaignPayload,
  type DiscountScope,
  type DiscountType,
} from '@/lib/api';

const inputClass = 'w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-pink-500';
const number = (value: number | string | null) =>
  value === null ? '—' : Number(value).toLocaleString('fa-IR');

type CampaignForm = {
  name: string;
  code: string;
  scope: DiscountScope;
  product: string;
  category: string;
  brand: string;
  discount_type: DiscountType;
  value: string;
  maximum_discount_amount: string;
  minimum_order_amount: string;
  starts_at: string;
  ends_at: string;
  priority: string;
  is_stackable: boolean;
  first_purchase_only: boolean;
  max_uses: string;
  per_user_limit: string;
  is_active: boolean;
};

function localDateValue(date: Date) {
  const adjusted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return adjusted.toISOString().slice(0, 16);
}

function emptyForm(): CampaignForm {
  const start = new Date();
  const end = new Date(start.getTime() + 30 * 24 * 60 * 60 * 1000);
  return {
    name: '', code: '', scope: 'product', product: '', category: '', brand: '',
    discount_type: 'percent', value: '10', maximum_discount_amount: '',
    minimum_order_amount: '0', starts_at: localDateValue(start),
    ends_at: localDateValue(end), priority: '100', is_stackable: false,
    first_purchase_only: false, max_uses: '', per_user_limit: '', is_active: true,
  };
}

function formFromCampaign(item: DiscountCampaign): CampaignForm {
  return {
    name: item.name, code: item.code ?? '', scope: item.scope,
    product: item.product?.toString() ?? '', category: item.category?.toString() ?? '',
    brand: item.brand?.toString() ?? '', discount_type: item.discount_type,
    value: String(item.value), maximum_discount_amount: item.maximum_discount_amount ?? '',
    minimum_order_amount: String(item.minimum_order_amount),
    starts_at: localDateValue(new Date(item.starts_at)),
    ends_at: localDateValue(new Date(item.ends_at)), priority: String(item.priority),
    is_stackable: item.is_stackable, first_purchase_only: item.first_purchase_only,
    max_uses: item.max_uses?.toString() ?? '',
    per_user_limit: item.per_user_limit?.toString() ?? '', is_active: item.is_active,
  };
}

function makePayload(form: CampaignForm): DiscountCampaignPayload {
  return {
    name: form.name.trim(),
    code: form.code.trim() ? form.code.trim().toUpperCase() : null,
    scope: form.scope,
    product: form.scope === 'product' && form.product ? Number(form.product) : null,
    category: form.scope === 'category' && form.category ? Number(form.category) : null,
    brand: form.scope === 'brand' && form.brand ? Number(form.brand) : null,
    discount_type: form.discount_type,
    value: form.value,
    maximum_discount_amount: form.maximum_discount_amount || null,
    minimum_order_amount: form.minimum_order_amount || '0',
    starts_at: new Date(form.starts_at).toISOString(),
    ends_at: new Date(form.ends_at).toISOString(),
    priority: Number(form.priority || 100),
    is_stackable: form.is_stackable,
    first_purchase_only: form.first_purchase_only,
    max_uses: form.max_uses ? Number(form.max_uses) : null,
    per_user_limit: form.per_user_limit ? Number(form.per_user_limit) : null,
    is_active: form.is_active,
  };
}

export default function DiscountsAdminPage() {
  const { token, user, loading: authLoading } = useAuth();
  const [campaigns, setCampaigns] = useState<DiscountCampaign[]>([]);
  const [form, setForm] = useState<CampaignForm>(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      setCampaigns(await fetchDiscountCampaigns(token));
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'دریافت کمپین‌ها انجام نشد.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (token && user?.is_staff) void load();
  }, [token, user, load]);

  const change = <K extends keyof CampaignForm>(key: K, value: CampaignForm[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const reset = () => {
    setForm(emptyForm());
    setEditingId(null);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) return;
    if (form.scope === 'product' && !form.product ||
        form.scope === 'category' && !form.category ||
        form.scope === 'brand' && !form.brand) {
      setError('برای دامنه انتخاب‌شده، شناسه هدف الزامی است.');
      return;
    }
    if (!form.starts_at || !form.ends_at || new Date(form.ends_at) <= new Date(form.starts_at)) {
      setError('زمان پایان باید بعد از زمان شروع باشد.');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const payload = makePayload(form);
      if (editingId) {
        await updateDiscountCampaign(token, editingId, payload);
        setNotice('کمپین تخفیف به‌روزرسانی شد.');
      } else {
        await createDiscountCampaign(token, payload);
        setNotice('کمپین تخفیف ایجاد شد.');
      }
      reset();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ذخیره کمپین انجام نشد.');
    } finally {
      setBusy(false);
    }
  };

  const edit = (item: DiscountCampaign) => {
    setEditingId(item.id);
    setForm(formFromCampaign(item));
    setError('');
    setNotice('');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const remove = async (item: DiscountCampaign) => {
    if (!token || !window.confirm(`کمپین «${item.name}» حذف شود؟`)) return;
    setBusy(true);
    setError('');
    try {
      await deleteDiscountCampaign(token, item.id);
      setNotice('کمپین حذف شد.');
      if (editingId === item.id) reset();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'حذف کمپین انجام نشد.');
    } finally {
      setBusy(false);
    }
  };

  if (authLoading) return <main className="grid min-h-[60vh] place-items-center">در حال بررسی دسترسی...</main>;
  if (!user || !token) return <main className="container mx-auto px-4 py-16 text-center">برای مدیریت تخفیف وارد حساب کاربری شوید.</main>;
  if (!user.is_staff) return <main className="container mx-auto px-4 py-16 text-center text-amber-800">این بخش فقط برای کاربران داخلی فروشگاه است.</main>;

  return (
    <main className="min-h-screen bg-page py-8" dir="rtl">
      <div className="container mx-auto max-w-7xl space-y-6 px-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="section-label">مدیریت فروشگاه</p>
            <h1 className="text-3xl font-bold text-pink-950">مدیریت تخفیف‌ها</h1>
            <p className="mt-2 text-sm text-gray-600">کمپین محصول، دسته، برند و سبد خرید؛ کد تخفیف و محدودیت مصرف</p>
          </div>
          <a href="/admin/pricing" className="rounded-xl border border-pink-200 bg-white px-4 py-2.5 text-sm font-bold text-pink-900">مدیریت قیمت‌گذاری</a>
        </header>

        {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
        {notice && <div role="status" className="rounded-xl border border-green-200 bg-green-50 p-3 text-sm text-green-800">{notice}</div>}

        <form onSubmit={submit} className="space-y-5 rounded-2xl border border-pink-100 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-bold text-gray-900">{editingId ? 'ویرایش کمپین' : 'ایجاد کمپین جدید'}</h2>
            {editingId && <button type="button" onClick={reset} className="text-sm font-bold text-pink-800">لغو ویرایش</button>}
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <label className="space-y-1 text-sm font-medium">نام کمپین<input required className={inputClass} value={form.name} onChange={(e) => change('name', e.target.value)} maxLength={160} /></label>
            <label className="space-y-1 text-sm font-medium">کد تخفیف (خالی = خودکار)<input className={inputClass} dir="ltr" value={form.code} onChange={(e) => change('code', e.target.value.toUpperCase())} maxLength={40} /></label>
            <label className="space-y-1 text-sm font-medium">دامنه تخفیف<select className={inputClass} value={form.scope} onChange={(e) => change('scope', e.target.value as DiscountScope)}><option value="product">محصول</option><option value="category">دسته‌بندی</option><option value="brand">برند</option><option value="cart">کل سبد خرید</option></select></label>

            {form.scope !== 'cart' && (
              <label className="space-y-1 text-sm font-medium">
                شناسه {form.scope === 'product' ? 'محصول' : form.scope === 'category' ? 'دسته‌بندی' : 'برند'}
                <input required type="number" min="1" className={inputClass} value={form.scope === 'product' ? form.product : form.scope === 'category' ? form.category : form.brand} onChange={(e) => {
                  if (form.scope === 'product') change('product', e.target.value);
                  else if (form.scope === 'category') change('category', e.target.value);
                  else if (form.scope === 'brand') change('brand', e.target.value);
                }} />
                <span className="block text-xs font-normal text-gray-500">شناسه عددی رکورد در کاتالوگ</span>
              </label>
            )}

            <label className="space-y-1 text-sm font-medium">نوع تخفیف<select className={inputClass} value={form.discount_type} onChange={(e) => change('discount_type', e.target.value as DiscountType)}><option value="percent">درصدی</option><option value="fixed">مبلغ ثابت (تومان)</option></select></label>
            <label className="space-y-1 text-sm font-medium">{form.discount_type === 'percent' ? 'درصد تخفیف' : 'مبلغ تخفیف (تومان)'}<input required type="number" min="1" max={form.discount_type === 'percent' ? 100 : undefined} className={inputClass} value={form.value} onChange={(e) => change('value', e.target.value)} /></label>
            <label className="space-y-1 text-sm font-medium">حداقل مبلغ کالاها (تومان)<input type="number" min="0" className={inputClass} value={form.minimum_order_amount} onChange={(e) => change('minimum_order_amount', e.target.value)} /></label>
            <label className="space-y-1 text-sm font-medium">سقف مبلغ تخفیف (اختیاری)<input type="number" min="1" className={inputClass} value={form.maximum_discount_amount} onChange={(e) => change('maximum_discount_amount', e.target.value)} /></label>
            <label className="space-y-1 text-sm font-medium">اولویت (عدد بیشتر = اولویت بالاتر)<input type="number" min="0" className={inputClass} value={form.priority} onChange={(e) => change('priority', e.target.value)} /></label>
            <label className="space-y-1 text-sm font-medium">شروع کمپین<input required type="datetime-local" className={inputClass} value={form.starts_at} onChange={(e) => change('starts_at', e.target.value)} /></label>
            <label className="space-y-1 text-sm font-medium">پایان کمپین<input required type="datetime-local" className={inputClass} value={form.ends_at} onChange={(e) => change('ends_at', e.target.value)} /></label>
            <label className="space-y-1 text-sm font-medium">حداکثر استفاده کل<input type="number" min="1" className={inputClass} placeholder="بدون محدودیت" value={form.max_uses} onChange={(e) => change('max_uses', e.target.value)} /></label>
            <label className="space-y-1 text-sm font-medium">حداکثر استفاده هر مشتری<input type="number" min="1" className={inputClass} placeholder="بدون محدودیت" value={form.per_user_limit} onChange={(e) => change('per_user_limit', e.target.value)} /></label>
          </div>

          <div className="flex flex-wrap gap-5 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" checked={form.is_stackable} onChange={(e) => change('is_stackable', e.target.checked)} /> قابل ترکیب با تخفیف دیگر</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={form.first_purchase_only} onChange={(e) => change('first_purchase_only', e.target.checked)} /> فقط اولین خرید</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={form.is_active} onChange={(e) => change('is_active', e.target.checked)} /> فعال</label>
          </div>

          <button disabled={busy} className="rounded-xl bg-pink-800 px-6 py-3 font-bold text-white disabled:opacity-50">{busy ? 'در حال ذخیره...' : editingId ? 'ذخیره تغییرات' : 'ایجاد کمپین'}</button>
        </form>

        <section className="rounded-2xl border border-pink-100 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-xl font-bold text-gray-900">کمپین‌های ثبت‌شده</h2>
            <button type="button" onClick={() => void load()} className="rounded-lg border border-pink-200 px-3 py-2 text-sm font-bold text-pink-900">بروزرسانی</button>
          </div>
          {loading ? <p className="py-8 text-center text-sm text-gray-500">در حال دریافت کمپین‌ها...</p> : campaigns.length === 0 ? <p className="py-8 text-center text-sm text-gray-500">هنوز کمپینی ثبت نشده است.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1050px] text-sm">
                <thead><tr className="border-b text-right text-gray-500"><th className="p-2">کمپین / کد</th><th className="p-2">دامنه</th><th className="p-2">تخفیف</th><th className="p-2">زمان</th><th className="p-2">مصرف</th><th className="p-2">وضعیت</th><th className="p-2">عملیات</th></tr></thead>
                <tbody>{campaigns.map((item) => <tr key={item.id} className="border-b border-gray-50 align-top">
                  <td className="p-2"><div className="font-bold">{item.name}</div><div className="font-mono text-xs text-gray-500" dir="ltr">{item.code || 'خودکار'}</div></td>
                  <td className="p-2">{({ product: 'محصول', category: 'دسته', brand: 'برند', cart: 'سبد خرید' })[item.scope]}</td>
                  <td className="p-2">{item.discount_type === 'percent' ? `${number(item.value)}٪` : `${number(item.value)} تومان`}</td>
                  <td className="p-2 whitespace-nowrap">{new Date(item.starts_at).toLocaleString('fa-IR')}<br />تا {new Date(item.ends_at).toLocaleString('fa-IR')}</td>
                  <td className="p-2">{number(item.usage_count)}{item.max_uses ? ` / ${number(item.max_uses)}` : ' / نامحدود'}</td>
                  <td className="p-2">{item.is_active ? 'فعال' : 'غیرفعال'}</td>
                  <td className="p-2"><div className="flex gap-2"><button type="button" onClick={() => edit(item)} className="rounded-lg border border-pink-200 px-3 py-1.5 font-bold text-pink-900">ویرایش</button><button type="button" disabled={busy} onClick={() => void remove(item)} className="rounded-lg border border-red-200 px-3 py-1.5 text-red-700 disabled:opacity-50">حذف</button></div></td>
                </tr>)}</tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
