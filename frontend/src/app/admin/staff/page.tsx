'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useAuth } from '@/context/AuthContext';

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const ROLES = ['مدیرعامل', 'رئیس هیئت‌مدیره', 'مدیر داخلی', 'حسابدار', 'مشاور', 'مشتری'] as const;
type Role = typeof ROLES[number];
type StaffUser = {
  id: number; mobile: string | null; username: string; first_name: string; last_name: string;
  full_name: string; roles: string[]; role: string; is_active: boolean; is_staff: boolean;
  is_superuser: boolean; date_joined: string;
};
type HistoryItem = {
  id: number; actor: string; target: string; previous_roles: string[];
  new_role: string; created_at: string;
};
type StaffResponse = { count: number; page: number; page_size: number; results: StaffUser[] };

class ApiRequestError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

const inputClass = 'w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none placeholder:text-slate-500 focus:border-pink-600 focus:ring-2 focus:ring-pink-100';
const buttonClass = 'rounded-xl border border-pink-200 bg-white px-4 py-2.5 text-sm font-bold text-pink-950 hover:bg-pink-50 disabled:opacity-50';
const number = (value: number) => new Intl.NumberFormat('fa-IR').format(value);
const date = (value: string) => new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
  dateStyle: 'medium', timeStyle: 'short',
}).format(new Date(value));

function getRequestErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) return 'نشست ورود معتبر نیست یا منقضی شده است. لطفاً خارج شوید و دوباره وارد شوید.';
    if (error.status === 403) return 'شما مجوز مدیریت کارکنان و مشاهده این اطلاعات را ندارید. این بخش فقط برای مدیرعامل یا رئیس هیئت‌مدیره مجاز است.';
    if (error.status >= 500) return 'سرور هنگام دریافت اطلاعات کارکنان با خطا مواجه شد. لطفاً کمی بعد دوباره تلاش کنید.';
    return error.message;
  }
  return error instanceof Error ? error.message : fallback;
}

export default function StaffManagementPage() {
  const { token, user, loading: authLoading } = useAuth();
  const [rows, setRows] = useState<StaffUser[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [draftRoles, setDraftRoles] = useState<Record<number, Role>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const request = useCallback(async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
    if (!token) throw new Error('نشست کاربری معتبر نیست.');
    const response = await fetch(`${API_URL}/auth/${path}`, {
      ...init,
      headers: {
        Authorization: `Token ${token}`,
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...init.headers,
      },
      cache: 'no-store',
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new ApiRequestError(data?.detail || 'درخواست با خطا مواجه شد.', response.status);
    }
    return data as T;
  }, [token]);

  const load = useCallback(async (preserveDrafts = false) => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const query = new URLSearchParams({ page: String(page) });
      if (search.trim()) query.set('search', search.trim());
      const [staff, events] = await Promise.all([
        request<StaffResponse>(`staff/?${query.toString()}`),
        request<HistoryItem[]>('staff/history/'),
      ]);
      setRows(staff.results);
      setCount(staff.count);
      setHistory(events);
      setDraftRoles(prev => Object.fromEntries(staff.results.map(row => [
        row.id,
        (preserveDrafts && prev[row.id] ? prev[row.id] : (row.roles.length === 1 ? row.roles[0] : 'مشتری')) as Role,
      ])));
    } catch (err) {
      setError(getRequestErrorMessage(err, 'دریافت اطلاعات کارکنان ناموفق بود.'));
    } finally {
      setLoading(false);
    }
  }, [token, page, search, request]);

  useEffect(() => { if (token) void load(); }, [token, load]);

  const saveRole = async (row: StaffUser) => {
    const role = draftRoles[row.id];
    if (!role || (row.roles.length === 1 && row.roles[0] === role)) return;
    setSaving(row.id);
    setError('');
    setNotice('');
    try {
      await request(`staff/${row.id}/role/`, {
        method: 'PATCH',
        body: JSON.stringify({ role }),
      });
      setNotice(`نقش ${row.full_name || row.mobile || row.username} به «${role}» تغییر کرد.`);
      await load(true);
    } catch (err) {
      setError(getRequestErrorMessage(err, 'تغییر نقش انجام نشد.'));
    } finally {
      setSaving(null);
    }
  };

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPage(1);
    void load();
  };

  if (authLoading) return <main className="grid min-h-[50vh] place-items-center">در حال بررسی دسترسی...</main>;
  if (!user || !token) return <main className="container mx-auto px-4 py-16 text-center">برای مدیریت کارکنان وارد حساب شوید.</main>;

  return (
    <main className="min-h-screen bg-page py-8" dir="rtl">
      <div className="container mx-auto max-w-7xl space-y-6 px-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="section-label">مدیریت فروشگاه</p>
            <h1 className="text-3xl font-bold text-pink-950">کارکنان و نقش‌ها</h1>
            <p className="mt-2 text-sm text-slate-600">تخصیص یکی از شش نقش استاندارد و مشاهده سوابق تغییر نقش</p>
          </div>
          <a href="/admin/inventory" className={buttonClass}>داشبورد انبار</a>
        </header>

        {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
        {notice && <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</div>}

        <section className="rounded-2xl border border-pink-200 bg-rose-50/60 p-4 shadow-sm sm:p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-slate-900">فهرست حساب‌ها</h2>
              <p className="mt-1 text-sm text-slate-600">{error ? 'تعداد حساب‌ها به دلیل خطای دریافت مشخص نیست.' : <>تعداد کل: {number(count)} · نمایش ۲۵ حساب در هر صفحه</>}</p>
            </div>
            <button type="button" className={buttonClass} onClick={() => void load()} disabled={loading}>به‌روزرسانی</button>
          </div>
          <form onSubmit={submitSearch} className="mb-4 flex flex-col gap-2 sm:flex-row">
            <input className={inputClass} value={search} onChange={event => setSearch(event.target.value)} placeholder="جست‌وجو با نام، نام خانوادگی یا شماره موبایل" />
            <button className="rounded-xl bg-pink-800 px-5 py-2.5 text-sm font-bold text-white hover:bg-pink-900">جست‌وجو</button>
          </form>
          <p className="mb-4 text-xs text-slate-600">
            هر بار ثبت نقش فقط روی همان حساب اعمال می‌شود؛ انتخاب‌های ذخیره‌نشده سایر حساب‌ها پس از ثبت حفظ می‌شوند.
          </p>

          {loading ? <p className="py-10 text-center text-slate-600">در حال دریافت اطلاعات...</p> : error ? (
            <div className="rounded-xl border border-red-200 bg-white p-8 text-center text-sm text-red-800">
              اطلاعات فهرست دریافت نشد. پس از رفع خطا، دکمه «به‌روزرسانی» را بزنید.
            </div>
          ) : rows.length === 0 ? (
            <p className="rounded-xl bg-white p-8 text-center text-slate-600">حسابی پیدا نشد.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] border-separate border-spacing-y-2 text-sm">
                <thead><tr className="text-right text-slate-600">
                  <th className="px-3 py-2">کاربر</th><th className="px-3 py-2">شماره موبایل</th>
                  <th className="px-3 py-2">وضعیت</th><th className="px-3 py-2">نقش فعلی</th>
                  <th className="px-3 py-2">نقش جدید</th><th className="px-3 py-2">عملیات</th>
                </tr></thead>
                <tbody>
                  {rows.map(row => (
                    <tr key={row.id} className="bg-white shadow-sm [&>td]:border-y [&>td]:border-pink-100 [&>td]:px-3 [&>td]:py-3 first:[&>td]:rounded-r-xl last:[&>td]:rounded-l-xl">
                      <td className="font-bold text-slate-900">{row.full_name || row.username}
                        {row.is_superuser && <span className="mr-2 rounded-md bg-amber-100 px-2 py-1 text-xs text-amber-900">مدیر سیستمی</span>}
                      </td>
                      <td dir="ltr" className="text-right text-slate-700">{row.mobile || '—'}</td>
                      <td><span className={row.is_active ? 'rounded-full bg-emerald-100 px-2.5 py-1 text-xs text-emerald-800' : 'rounded-full bg-red-100 px-2.5 py-1 text-xs text-red-800'}>{row.is_active ? 'فعال' : 'غیرفعال'}</span></td>
                      <td className="text-slate-700">{row.roles.length ? row.roles.join('، ') : 'بدون نقش'}</td>
                      <td>
                        <select className={inputClass} value={draftRoles[row.id] ?? 'مشتری'} disabled={row.is_superuser || row.id === user.id} onChange={event => setDraftRoles(prev => ({ ...prev, [row.id]: event.target.value as Role }))}>
                          {ROLES.map(role => <option key={role} value={role}>{role}</option>)}
                        </select>
                      </td>
                      <td><button type="button" className="rounded-lg bg-pink-800 px-3 py-2 text-xs font-bold text-white disabled:opacity-40" disabled={saving === row.id || row.is_superuser || row.id === user.id || (row.roles.length === 1 && row.roles[0] === draftRoles[row.id])} onClick={() => void saveRole(row)}>{saving === row.id ? 'در حال ذخیره...' : 'ثبت نقش'}</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-4 flex items-center justify-between gap-3">
            <button type="button" className={buttonClass} disabled={page <= 1 || loading || Boolean(error)} onClick={() => setPage(value => Math.max(1, value - 1))}>صفحه قبل</button>
            <span className="text-sm text-slate-600">صفحه {number(page)} از {number(Math.max(1, Math.ceil(count / 25)))}</span>
            <button type="button" className={buttonClass} disabled={page * 25 >= count || loading || Boolean(error)} onClick={() => setPage(value => value + 1)}>صفحه بعد</button>
          </div>
        </section>

        <section className="rounded-2xl border border-sky-200 bg-sky-50/60 p-4 shadow-sm sm:p-6">
          <h2 className="text-xl font-bold text-slate-900">سوابق تغییر نقش</h2>
          <p className="mt-1 text-sm text-slate-600">۵۰ تغییر آخر به همراه ثبت‌کننده، نقش قبلی و نقش جدید</p>
          {error ? <p className="mt-4 rounded-xl border border-red-200 bg-white p-5 text-sm text-red-800">سوابق نیز به دلیل خطای دریافت در دسترس نیست.</p> : history.length === 0 ? <p className="mt-4 rounded-xl bg-white p-5 text-sm text-slate-600">هنوز تغییری ثبت نشده است.</p> : (
            <div className="mt-4 space-y-2">
              {history.map(item => (
                <article key={item.id} className="rounded-xl border border-sky-100 bg-white p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <strong className="text-slate-900">{item.target}</strong>
                    <time className="text-xs text-slate-500">{date(item.created_at)}</time>
                  </div>
                  <p className="mt-2 text-slate-700">تغییر توسط {item.actor}: {item.previous_roles.join('، ') || 'بدون نقش'} ← <strong className="text-pink-900">{item.new_role}</strong></p>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
