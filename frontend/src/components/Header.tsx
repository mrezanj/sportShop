'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useCart } from '@/context/CartContext';
import { useAuth } from '@/context/AuthContext';
import type { Category } from '@/lib/api';

export default function Header({ categories }: { categories: Category[] }) {
  const pathname = usePathname();
  const { totalItems } = useCart();
  const { user, loading, isAuthenticated, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

  // Auto-close mobile menu on route change
  useEffect(() => {
    setMenuOpen(false);
    setMoreOpen(false);
  }, [pathname]);

  // Lock body scroll when mobile menu is open
  useEffect(() => {
    if (menuOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [menuOpen]);

  // Close "more" dropdown on outside click
  useEffect(() => {
    if (!moreOpen) return;
    const close = () => setMoreOpen(false);
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, [moreOpen]);

  return (
    <>
      <header className="site-header bg-white/95 backdrop-blur-md border-b border-pink-100 shadow-[var(--shadow-header)] sticky top-0 z-40">
        <div className="container mx-auto px-3 sm:px-4 py-3 flex items-center justify-between gap-2 sm:gap-4">
          {/* Mobile hamburger */}
          <button
            onClick={() => setMenuOpen(true)}
            className="lg:hidden w-10 h-10 rounded-lg hover:bg-pink-50 flex items-center justify-center text-pink-900 flex-shrink-0"
            aria-label="باز کردن منو"
          >
            <svg
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
            >
              <path d="M3 6h18M3 12h18M3 18h18" />
            </svg>
          </button>

          {/* Logo */}
          <Link href="/" className="flex-shrink-0 flex items-center group">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo.png"
              alt="مادوان | Madone"
              className="h-12 sm:h-14 w-auto max-w-[180px] object-contain group-hover:scale-105 transition-transform"
            />
          </Link>

          {/* Desktop nav */}
          <nav className="hidden lg:flex items-center gap-1 text-sm font-medium overflow-x-auto flex-1 justify-center">
            <NavLink href="/products" active={pathname === '/products'}>
              همه محصولات
            </NavLink>
            {categories.slice(0, 4).map((cat) => (
              <NavLink
                key={cat.id}
                href={`/products?category=${cat.slug}`}
                active={false}
              >
                {cat.name}
              </NavLink>
            ))}
            {categories.length > 4 && (
              <div
                className="relative"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => setMoreOpen(!moreOpen)}
                  className={`relative px-3 py-2 rounded-lg transition-colors whitespace-nowrap flex items-center gap-1 ${
                    moreOpen
                      ? 'text-pink-900 font-bold bg-pink-50'
                      : 'text-gray-700 hover:text-pink-800 hover:bg-pink-50/60'
                  }`}
                >
                  بیشتر
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={`transition-transform ${
                      moreOpen ? 'rotate-180' : ''
                    }`}
                  >
                    <path d="m6 9 6 6 6-6" />
                  </svg>
                </button>
                {moreOpen && (
                  <div className="absolute top-full right-0 mt-2 bg-white rounded-xl shadow-xl border border-pink-100 py-2 min-w-[220px] z-50 animate-fade-in-down">
                    {categories.slice(4).map((cat) => (
                      <Link
                        key={cat.id}
                        href={`/products?category=${cat.slug}`}
                        className="block px-4 py-2 text-sm text-gray-700 hover:bg-pink-50 hover:text-pink-800 transition-colors"
                        onClick={() => setMoreOpen(false)}
                      >
                        {cat.name}
                      </Link>
                    ))}
                    <div className="border-t border-pink-100 mt-1 pt-1">
                      <Link
                        href="/products"
                        className="block px-4 py-2 text-sm font-bold text-pink-800 hover:bg-pink-50 transition-colors"
                        onClick={() => setMoreOpen(false)}
                      >
                        مشاهده همه محصولات →
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            )}
          </nav>

          {/* Actions */}
          <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
            {user?.is_staff && (
              <Link
                href="/admin/inventory"
                className="hidden md:inline-flex rounded-lg border border-pink-200 px-3 py-2 text-sm font-semibold text-pink-900 hover:bg-pink-50"
              >
                پنل انبار
              </Link>
            )}
            {loading ? (
              <span className="text-xs text-gray-400">...</span>
            ) : isAuthenticated && user ? (
              <div className="flex items-center gap-1">
                <Link
                  href="/account"
                  className="text-sm text-gray-700 hover:text-pink-800 px-2 sm:px-3 py-2 rounded-lg hover:bg-pink-50 transition-colors hidden sm:inline-flex items-center gap-1.5"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                  <span className="hidden md:inline">{user.mobile}</span>
                  <span className="md:hidden">حساب</span>
                </Link>
                <button
                  onClick={logout}
                  className="text-sm text-gray-600 hover:text-red-700 px-2 py-2 rounded-lg hover:bg-red-50 transition-colors hidden sm:inline"
                >
                  خروج
                </button>
              </div>
            ) : (
              <Link
                href="/login"
                className="text-sm font-semibold text-pink-800 hover:text-pink-900 px-2 sm:px-4 py-2 rounded-lg hover:bg-pink-50 transition-colors"
              >
                <span className="hidden sm:inline">ورود / ثبت‌نام</span>
                <span className="sm:hidden">ورود</span>
              </Link>
            )}

            <Link
              href="/cart"
              className="relative flex items-center gap-2 bg-gradient-to-br from-pink-800 to-pink-900 hover:from-pink-900 hover:to-pink-950 text-white px-3 sm:px-4 py-2.5 rounded-xl transition-all shadow-md hover:shadow-lg hover:-translate-y-0.5"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="9" cy="21" r="1" />
                <circle cx="20" cy="21" r="1" />
                <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
              </svg>
              <span className="text-sm font-bold hidden sm:inline">
                سبد خرید
              </span>
              {totalItems > 0 && (
                <span className="absolute -top-1.5 -right-1.5 bg-white text-pink-900 text-xs font-extrabold rounded-full min-w-6 h-6 px-1.5 flex items-center justify-center shadow-lg border-2 border-pink-800">
                  {totalItems.toLocaleString('fa-IR')}
                </span>
              )}
            </Link>
          </div>
        </div>
      </header>

      {/* Mobile drawer */}
      {menuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden print:hidden">
          <div
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            onClick={() => setMenuOpen(false)}
          />
          <div className="absolute top-0 right-0 h-full w-80 max-w-[85vw] bg-white shadow-2xl flex flex-col animate-slide-in-right">
            <div className="p-4 border-b border-pink-100 flex items-center justify-between flex-shrink-0">
              <span className="font-bold text-pink-900 text-base">منو</span>
              <button
                onClick={() => setMenuOpen(false)}
                className="w-9 h-9 rounded-lg hover:bg-pink-50 flex items-center justify-center text-pink-900"
                aria-label="بستن منو"
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                >
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            <nav className="flex-1 overflow-y-auto p-4 space-y-1">
              <MobileLink href="/" active={pathname === '/'}>
                خانه
              </MobileLink>
              <MobileLink
                href="/products"
                active={pathname === '/products'}
              >
                همه محصولات
              </MobileLink>

              <div className="pt-4 mt-4 border-t border-pink-100">
                <p className="text-[11px] font-bold text-pink-700 uppercase tracking-widest mb-2 px-3">
                  دسته‌بندی‌ها
                </p>
                {categories.map((cat) => (
                  <MobileLink
                    key={cat.id}
                    href={`/products?category=${cat.slug}`}
                    active={false}
                  >
                    {cat.name}
                  </MobileLink>
                ))}
              </div>

              {user?.is_staff && (
                <div className="pt-4 mt-4 border-t border-pink-100">
                  <MobileLink href="/admin/inventory" active={pathname === '/admin/inventory'}>
                    داشبورد انبار
                  </MobileLink>
                </div>
              )}

              <div className="pt-4 mt-4 border-t border-pink-100">
                <MobileLink
                  href="/account"
                  active={pathname === '/account'}
                >
                  حساب کاربری
                </MobileLink>
                <MobileLink href="/cart" active={pathname === '/cart'}>
                  سبد خرید
                </MobileLink>
              </div>
            </nav>

            <div className="p-4 border-t border-pink-100 flex-shrink-0">
              {isAuthenticated && user ? (
                <>
                  <p className="text-xs text-gray-500 mb-2">
                    وارد شده با {user.mobile}
                  </p>
                  <button
                    onClick={() => {
                      logout();
                      setMenuOpen(false);
                    }}
                    className="w-full text-sm text-red-600 hover:text-red-800 border border-red-200 rounded-lg py-2 bg-white font-medium transition-colors"
                  >
                    خروج از حساب
                  </button>
                </>
              ) : (
                <Link
                  href="/login"
                  className="block w-full text-center text-sm bg-pink-800 hover:bg-pink-900 text-white font-semibold py-2.5 rounded-lg transition-colors"
                >
                  ورود / ثبت‌نام
                </Link>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function NavLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`relative px-3 py-2 rounded-lg transition-colors whitespace-nowrap ${
        active
          ? 'text-pink-900 font-bold bg-pink-50'
          : 'text-gray-700 hover:text-pink-800 hover:bg-pink-50/60'
      }`}
    >
      {children}
    </Link>
  );
}

function MobileLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`block px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
        active
          ? 'bg-pink-50 text-pink-900 font-bold'
          : 'text-gray-700 hover:bg-pink-50 hover:text-pink-800'
      }`}
    >
      {children}
    </Link>
  );
}