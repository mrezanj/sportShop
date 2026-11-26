'use client';

import { Suspense, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import { fetchInvoice, type InvoiceRecord } from '@/lib/api';

function money(value?: string) {
  const amount = Number(value ?? 0);
  return Number.isFinite(amount) ? amount.toLocaleString('fa-IR') : '—';
}

function detail(label: string, value?: string) {
  return (
    <div className="flex justify-between gap-4 border-b border-gray-100 py-2 text-sm last:border-0">
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-900 text-left break-words">{value || 'ثبت نشده'}</span>
    </div>
  );
}

function InvoicePageContent() {
  const params = useParams();
  const router = useRouter();
  const orderNumber = params.orderNumber as string;
  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const [invoice, setInvoice] = useState<InvoiceRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push(`/login?returnTo=/account/orders/${orderNumber}/invoice`);
    }
  }, [authLoading, isAuthenticated, router, orderNumber]);

  useEffect(() => {
    if (!token || !orderNumber) return;
    fetchInvoice(orderNumber, token)
      .then(setInvoice)
      .catch((err) => setError(err instanceof Error ? err.message : 'دریافت فاکتور ناموفق بود.'))
      .finally(() => setLoading(false));
  }, [token, orderNumber]);

  if (authLoading || loading) {
    return <div className="min-h-screen flex items-center justify-center text-gray-500">در حال بارگذاری فاکتور...</div>;
  }

  if (error || !invoice) {
    return (
      <main dir="rtl" className="min-h-screen flex items-center justify-center p-6">
        <div className="text-center">
          <p className="text-gray-700 mb-4">{error || 'فاکتور یافت نشد.'}</p>
          <Link className="text-pink-800" href={`/account/orders/${orderNumber}`}>بازگشت به سفارش</Link>
        </div>
      </main>
    );
  }

  const { snapshot } = invoice;
  const seller = snapshot.seller;
  const buyer = snapshot.buyer;
  const totals = snapshot.totals;

  return (
    <main dir="rtl" className="invoice-page-root min-h-screen bg-gray-100 py-8 print:bg-white print:py-0">
      <div className="invoice-page-shell mx-auto max-w-5xl px-4 print:max-w-none print:px-0">
        <div className="invoice-screen-actions mb-4 flex items-center justify-between print:hidden">
          <Link href={`/account/orders/${orderNumber}`} className="text-sm text-pink-800 hover:underline">بازگشت به سفارش</Link>
          <button onClick={() => window.print()} className="rounded-lg bg-pink-800 px-5 py-2.5 text-sm font-semibold text-white hover:bg-pink-900">چاپ فاکتور</button>
        </div>

        <article className="invoice-paper bg-white p-6 shadow-sm sm:p-10 print:p-0 print:shadow-none">
          <header className="flex flex-wrap items-start justify-between gap-6 border-b-2 border-gray-800 pb-6">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">فاکتور فروش</h1>
              <p className="mt-2 text-xs text-gray-500">فاکتور داخلی فروشگاه</p>
            </div>
            <div className="text-left text-sm">
              <p className="text-gray-500">شماره فاکتور</p>
              <p dir="ltr" className="mt-1 font-bold text-gray-900">{invoice.invoice_number}</p>
              <p className="mt-2 text-gray-500">تاریخ صدور</p>
              <p className="mt-1 text-gray-900">{new Date(invoice.issued_at).toLocaleString('fa-IR')}</p>
              <p className="mt-2 text-gray-500">شماره سفارش</p>
              <p dir="ltr" className="mt-1 font-semibold text-gray-900">{snapshot.order_number}</p>
            </div>
          </header>

          <div className="invoice-notice my-6 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm leading-7 text-amber-900 print:bg-white">
            {snapshot.notice}
          </div>

          <section className="invoice-party-grid grid gap-6 sm:grid-cols-2">
            <div className="invoice-party-card rounded-lg border border-pink-100 p-4">
              <h2 className="mb-2 font-bold text-gray-900">فروشنده</h2>
              {detail('نام', seller.name)}
              {detail('شناسه ملی', seller.national_id)}
              {detail('شناسه اقتصادی', seller.economic_code)}
              {detail('شماره ثبت', seller.registration_number)}
              {detail('تلفن', seller.phone)}
              {detail('نشانی', seller.address)}
              {detail('کد پستی', seller.postal_code)}
            </div>
            <div className="invoice-party-card rounded-lg border border-pink-100 p-4">
              <h2 className="mb-2 font-bold text-gray-900">خریدار / گیرنده</h2>
              {detail('نام', buyer.name)}
              {detail('موبایل', buyer.mobile)}
              {detail('استان', buyer.province)}
              {detail('شهر', buyer.city)}
              {detail('نشانی', buyer.address)}
              {detail('کد پستی', buyer.postal_code)}
            </div>
          </section>

          <section className="invoice-items-section mt-8">
            <h2 className="mb-3 font-bold text-gray-900">اقلام فاکتور</h2>
            <div className="invoice-items-scroll overflow-x-auto">
              <table className="invoice-items-table w-full min-w-[760px] border-collapse text-sm">
                <colgroup>
                  <col style={{ width: '6%' }} />
                  <col style={{ width: '27%' }} />
                  <col style={{ width: '12%' }} />
                  <col style={{ width: '7%' }} />
                  <col style={{ width: '16%' }} />
                  <col style={{ width: '15%' }} />
                  <col style={{ width: '17%' }} />
                </colgroup>
                <thead>
                  <tr className="bg-gray-100 text-gray-700">
                    <th className="border border-gray-200 p-2">ردیف</th>
                    <th className="border border-gray-200 p-2 text-right">شرح کالا</th>
                    <th className="border border-gray-200 p-2">SKU</th>
                    <th className="border border-gray-200 p-2">تعداد</th>
                    <th className="border border-gray-200 p-2">قیمت واحد (تومان)</th>
                    <th className="border border-gray-200 p-2">تخفیف (تومان)</th>
                    <th className="border border-gray-200 p-2">مبلغ نهایی (تومان)</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshot.items.map((item, index) => (
                    <tr key={item.order_item_id}>
                      <td className="border border-gray-200 p-2 text-center">{(index + 1).toLocaleString('fa-IR')}</td>
                      <td className="border border-gray-200 p-2">
                        <p className="font-medium text-gray-900">{item.product_name}</p>
                        <p className="mt-1 text-xs text-gray-500">{item.brand_name} {item.variant_label}</p>
                      </td>
                      <td dir="ltr" className="border border-gray-200 p-2 text-center">{item.sku || '—'}</td>
                      <td className="border border-gray-200 p-2 text-center">{item.quantity.toLocaleString('fa-IR')}</td>
                      <td className="border border-gray-200 p-2 text-left">{money(item.unit_price)}</td>
                      <td className="border border-gray-200 p-2 text-left">{money(item.discount_amount)}</td>
                      <td className="border border-gray-200 p-2 text-left font-semibold">{money(item.final_subtotal)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="invoice-totals mt-8 ml-auto mr-0 w-full max-w-lg rounded-xl border border-gray-200 bg-gray-50/80 p-4 space-y-2 text-sm">
            {detail('جمع کالاها', money(totals.subtotal) + ' تومان')}
            {detail('تخفیف', money(totals.discount_amount) + ' تومان')}
            {detail('مالیات محاسبه‌شده', money(totals.vat_amount) + ' تومان')}
            {detail('هزینه ارسال', money(totals.shipping_cost) + ' تومان')}
            {detail('هزینه بسته‌بندی', money(totals.packaging_cost) + ' تومان')}
            <div className="flex justify-between border-t-2 border-gray-800 pt-3 text-base font-bold">
              <span>مبلغ نهایی پرداخت‌شده</span>
              <span>{money(totals.total_amount)} تومان</span>
            </div>
          </section>

          <footer className="invoice-print-footer mt-10 border-t border-gray-200 pt-4 text-xs leading-6 text-gray-500">
            <p>شناسه پرداخت: <span dir="ltr">{snapshot.payment.reference || '—'}</span></p>
            <p>این فاکتور بر اساس اطلاعات ثبت‌شده هنگام سفارش تهیه شده است. اطلاعات هویتی یا ثبتی فروشنده که هنوز در سامانه پیکربندی نشده، در این نسخه خالی نمایش داده می‌شود.</p>
          </footer>
        </article>
      </div>
      <style jsx global>{`
        @media print {
          @page {
            size: A4 landscape;
            margin: 7mm;
          }

          html,
          body {
            width: 100% !important;
            min-width: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            background: #fff !important;
          }

          body:has(.invoice-page-root) {
            display: block !important;
            position: static !important;
            overflow: visible !important;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }

          body:has(.invoice-page-root) .site-header,
          body:has(.invoice-page-root) .site-footer,
          body:has(.invoice-page-root) .invoice-screen-actions {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
          }

          .invoice-page-root {
            display: block !important;
            width: 100% !important;
            min-height: 0 !important;
            height: auto !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: visible !important;
            background: #fff !important;
          }

          .invoice-page-shell {
            display: block !important;
            width: 100% !important;
            max-width: none !important;
            margin: 0 !important;
            padding: 0 !important;
          }

          .invoice-paper {
            display: block !important;
            width: 100% !important;
            max-width: none !important;
            margin: 0 !important;
            padding: 0 !important;
            border: 0 !important;
            border-radius: 0 !important;
            background: #fff !important;
            box-shadow: none !important;
          }

          .invoice-paper > header {
            display: flex !important;
            flex-wrap: nowrap !important;
            justify-content: space-between !important;
            gap: 8mm !important;
            padding-bottom: 4mm !important;
          }

          .invoice-party-grid {
            display: grid !important;
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            gap: 4mm !important;
          }

          .invoice-party-card {
            min-width: 0 !important;
            padding: 3mm !important;
            break-inside: avoid;
            page-break-inside: avoid;
          }

          .invoice-notice {
            margin: 3mm 0 !important;
            padding: 2mm 3mm !important;
            background: #fff !important;
          }

          .invoice-items-section {
            width: 100% !important;
            margin-top: 4mm !important;
          }

          .invoice-items-scroll {
            width: 100% !important;
            overflow: visible !important;
          }

          .invoice-items-table {
            display: table !important;
            width: 100% !important;
            min-width: 0 !important;
            max-width: 100% !important;
            table-layout: fixed !important;
            border-collapse: collapse !important;
            font-size: 7.5pt !important;
          }

          .invoice-items-table th,
          .invoice-items-table td {
            box-sizing: border-box !important;
            padding: 1.6mm 1mm !important;
            white-space: normal !important;
            overflow-wrap: anywhere !important;
            word-break: normal !important;
            line-height: 1.45 !important;
            vertical-align: middle !important;
          }

          .invoice-items-table th {
            font-weight: 700 !important;
          }

          .invoice-items-table th:nth-child(5),
          .invoice-items-table th:nth-child(6),
          .invoice-items-table th:nth-child(7),
          .invoice-items-table td:nth-child(5),
          .invoice-items-table td:nth-child(6),
          .invoice-items-table td:nth-child(7) {
            direction: ltr !important;
            text-align: right !important;
            font-variant-numeric: tabular-nums;
          }

          .invoice-items-table tr {
            break-inside: avoid;
            page-break-inside: avoid;
          }

          .invoice-totals {
            width: 100% !important;
            max-width: 120mm !important;
            margin-top: 4mm !important;
            margin-left: auto !important;
            margin-right: 0 !important;
            padding: 3mm !important;
            border: 0.3mm solid #e5e7eb !important;
            border-radius: 3mm !important;
            background: #f9fafb !important;
            break-inside: avoid;
            page-break-inside: avoid;
          }

          .invoice-print-footer {
            margin-top: 5mm !important;
            padding-top: 2mm !important;
            break-inside: avoid;
            page-break-inside: avoid;
          }

          a {
            color: inherit !important;
            text-decoration: none !important;
          }
        }
      `}</style>
    </main>
  );
}


export default function InvoicePage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-gray-500">
          در حال بارگذاری فاکتور...
        </div>
      }
    >
      <InvoicePageContent />
    </Suspense>
  );
}
