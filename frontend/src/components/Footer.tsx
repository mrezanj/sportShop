'use client';

import Link from 'next/link';
import type { Category } from '@/lib/api';

export default function Footer({ categories }: { categories: Category[] }) {
  const persianYear = new Intl.DateTimeFormat('fa-IR', {
    year: 'numeric',
  }).format(new Date());

  const quickLinks = [
    { href: '/about', label: 'درباره ما' },
    { href: '/contact', label: 'تماس با ما' },
    { href: '/faq', label: 'سوالات متداول' },
    { href: '/guide', label: 'راهنمای خرید' },
    { href: '/track-order', label: 'پیگیری سفارش' },
    { href: '/returns', label: 'شرایط بازگشت کالا' },
    { href: '/terms', label: 'قوانین و مقررات' },
    { href: '/privacy', label: 'حریم خصوصی' },
    { href: '/cooperation', label: 'همکاری با ما' },
  ];

  return (
    <footer className="site-footer relative mt-16 bg-gradient-to-br from-pink-950 via-pink-900 to-pink-950 text-pink-100 overflow-hidden">
      {/* Decorative blobs */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-32 -right-32 w-96 h-96 rounded-full bg-pink-500/10 blur-3xl" />
        <div className="absolute -bottom-32 -left-32 w-96 h-96 rounded-full bg-pink-400/10 blur-3xl" />
        <div
          className="absolute inset-0 opacity-10"
          style={{
            backgroundImage:
              'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.4) 1px, transparent 0)',
            backgroundSize: '28px 28px',
          }}
        />
      </div>

      <div className="container mx-auto px-4 py-14 relative">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-10">
          {/* Col 1: Logo + description + social + Enamad */}
          <div>
            <Link
              href="/"
              className="inline-block bg-white rounded-xl p-2 mb-4 hover:scale-105 transition-transform"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/logo.png"
                alt="مادوان | Madone"
                className="h-14 w-auto max-w-[180px] object-contain"
              />
            </Link>

            <p className="text-sm text-pink-100/80 leading-relaxed mb-5">
              مرجع تخصصی مکمل‌های ورزشی، پوشاک و تجهیزات باشگاهی — با مجوز
              بهداشت و تضمین اصالت کالا، ارسال به سراسر ایران.
            </p>

            <div className="flex items-center gap-2 mb-5">
              <a
                href="https://instagram.com"
                target="_blank"
                rel="noopener noreferrer"
                className="w-10 h-10 rounded-lg bg-white/10 hover:bg-white/20 border border-white/20 flex items-center justify-center transition-colors"
                aria-label="اینستاگرام"
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
                  <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
                  <line x1="17.5" y1="6.5" x2="17.51" y2="6.5" />
                </svg>
              </a>
              <a
                href="tel:08112345678"
                className="w-10 h-10 rounded-lg bg-white/10 hover:bg-white/20 border border-white/20 flex items-center justify-center transition-colors"
                aria-label="تماس"
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
                </svg>
              </a>
              <a
                href="mailto:info@example.com"
                className="w-10 h-10 rounded-lg bg-white/10 hover:bg-white/20 border border-white/20 flex items-center justify-center transition-colors"
                aria-label="ایمیل"
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                  <polyline points="22,6 12,13 2,6" />
                </svg>
              </a>
            </div>

            {/* Enamad placeholder */}
            <div>
              <p className="text-[10px] text-pink-200/70 mb-2 uppercase tracking-wider">
                نماد اعتماد الکترونیکی
              </p>
              <div className="bg-white/10 border-2 border-white/20 border-dashed rounded-xl w-20 h-20 flex items-center justify-center text-[10px] text-pink-200/60 text-center leading-tight p-2">
                به‌زودی
                <br />
                ای‌نماد
              </div>
            </div>
          </div>

          {/* Col 2: Quick links */}
          <div>
            <h3 className="font-bold text-white mb-4 text-sm">دسترسی سریع</h3>
            <ul className="space-y-2 text-sm">
              {quickLinks.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-pink-100/80 hover:text-white transition-colors"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Col 3: Categories */}
          <div>
            <h3 className="font-bold text-white mb-4 text-sm">
              دسته‌بندی محصولات
            </h3>
            <ul className="space-y-2 text-sm">
              {categories.slice(0, 6).map((cat) => (
                <li key={cat.id}>
                  <Link
                    href={`/products?category=${cat.slug}`}
                    className="text-pink-100/80 hover:text-white transition-colors"
                  >
                    {cat.name}
                  </Link>
                </li>
              ))}
              {categories.length > 6 && (
                <li>
                  <Link
                    href="/products"
                    className="text-pink-300 hover:text-white font-medium transition-colors"
                  >
                    مشاهده همه →
                  </Link>
                </li>
              )}
            </ul>
          </div>

          {/* Col 4: Contact */}
          <div>
            <h3 className="font-bold text-white mb-4 text-sm">
              اطلاعات تماس
            </h3>
            <ul className="space-y-3 text-sm text-pink-100/90">
              <li className="flex items-start gap-2">
                <span className="text-pink-300 flex-shrink-0 mt-0.5">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                    <circle cx="12" cy="10" r="3" />
                  </svg>
                </span>
                <span className="leading-relaxed">
                  همدان، خیابان ...، پلاک ...
                </span>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-pink-300 flex-shrink-0">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
                  </svg>
                </span>
                <a
                  href="tel:08112345678"
                  dir="ltr"
                  className="hover:text-white transition-colors"
                >
                  081-12345678
                </a>
              </li>
              <li className="flex items-center gap-2">
                <span className="text-pink-300 flex-shrink-0">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                    <polyline points="22,6 12,13 2,6" />
                  </svg>
                </span>
                <a
                  href="mailto:info@example.com"
                  dir="ltr"
                  className="hover:text-white transition-colors"
                >
                  info@example.com
                </a>
              </li>
            </ul>

            <div className="mt-5 pt-4 border-t border-white/10">
              <p className="text-[11px] text-pink-200/70 leading-relaxed">
                پاسخگویی: شنبه تا پنجشنبه
                <br />
                ۹ صبح تا ۶ عصر
              </p>
            </div>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="mt-12 pt-6 border-t border-white/10 flex flex-col md:flex-row items-center justify-between gap-3 text-xs text-pink-200/70">
          <p>© {persianYear} مادوان (Madone). تمامی حقوق محفوظ است.</p>
          <p className="flex items-center gap-1">
            ساخته شده با <span className="text-pink-400">♥</span> برای
            ورزشکاران ایران
          </p>
        </div>
      </div>
    </footer>
  );
}