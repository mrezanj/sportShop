export const instant = false;

import Link from 'next/link';
import {
  fetchHomepageData,
  toAbsoluteUrl,
  type Product,
  type Testimonial,
} from '@/lib/api';
import AnimatedCounter from '@/components/AnimatedCounter';
import TestimonialsSlider from '@/components/TestimonialsSlider';

export default async function HomePage() {
  const data = await fetchHomepageData();

  // Merge bestsellers + new products, unique, up to 3 for hero
  const merged = [...data.bestsellers, ...data.new_products];
  const seen = new Set<number>();
  const heroProducts = merged
    .filter((p) => {
      if (seen.has(p.id)) return false;
      seen.add(p.id);
      return true;
    })
    .slice(0, 3);

  return (
    <div className="min-h-screen bg-page">
      {/* ===== HERO ===== */}
      <section className="relative overflow-hidden bg-gradient-to-br from-pink-950 via-pink-900 to-pink-800 text-white">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-40 -right-40 w-[500px] h-[500px] rounded-full bg-pink-500/20 blur-3xl" />
          <div className="absolute -bottom-40 -left-40 w-[400px] h-[400px] rounded-full bg-pink-400/10 blur-3xl" />
          <div
            className="absolute inset-0 opacity-15"
            style={{
              backgroundImage:
                'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.4) 1px, transparent 0)',
              backgroundSize: '32px 32px',
            }}
          />
        </div>

        <div className="container mx-auto px-4 py-16 md:py-24 relative">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            {/* Text column */}
            <div>
              <p className="inline-flex items-center gap-2 bg-white/10 backdrop-blur-sm border border-white/20 rounded-full px-4 py-1.5 text-[11px] font-bold tracking-widest uppercase mb-6 animate-gentle-pulse">
                <span className="w-1.5 h-1.5 rounded-full bg-pink-300" />
               تنها مرجع فروش محصولات ورزشی
              </p>

              <h1 className="text-4xl md:text-5xl lg:text-6xl font-black leading-[1.15] mb-6">
                قدرتت را
                <br />
                <span className="text-pink-200">چند برابر کن</span>
              </h1>

              <p className="text-base md:text-lg text-pink-100/90 leading-relaxed mb-8 max-w-lg">
                مکمل‌های اصل با مجوز بهداشت، پوشاک ورزشی حرفه‌ای و تجهیزات
                تخصصی باشگاهی — همراه با مشاوره رایگان از کارشناسان تغذیه
                ورزشی.
              </p>

              <div className="flex flex-wrap gap-3">
                <Link
                  href="/products"
                  className="group inline-flex items-center gap-2 bg-white text-pink-900 hover:bg-pink-100 font-bold px-7 py-3 rounded-xl shadow-lg hover:shadow-xl transition-all hover:-translate-y-0.5"
                >
                  مشاهده محصولات
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="transition-transform group-hover:-translate-x-1"
                  >
                    <path d="M15 18l-6-6 6-6" />
                  </svg>
                </Link>
                <Link
                  href="/products"
                  className="inline-flex items-center gap-2 bg-white/10 backdrop-blur-sm border border-white/30 text-white hover:bg-white/20 font-bold px-7 py-3 rounded-xl transition-all hover:-translate-y-0.5"
                >
                  مشاوره تخصصی
                </Link>
              </div>

              {/* Animated Stats */}
              <div className="grid grid-cols-3 gap-4 mt-10 max-w-md">
                <div>
                  <p className="text-2xl md:text-3xl font-black text-pink-200">
                    <AnimatedCounter end={20} suffix="+" />
                  </p>
                  <p className="text-[11px] md:text-xs text-pink-200/80 mt-1">
                    برند معتبر
                  </p>
                </div>
                <div>
                  <p className="text-2xl md:text-3xl font-black text-pink-200">
                    <AnimatedCounter end={100} suffix="٪" />
                  </p>
                  <p className="text-[11px] md:text-xs text-pink-200/80 mt-1">
                    اصالت کالا
                  </p>
                </div>
                <div>
                  <p className="text-2xl md:text-3xl font-black text-pink-200">
                    <AnimatedCounter end={31} />
                  </p>
                  <p className="text-[11px] md:text-xs text-pink-200/80 mt-1">
                    استان تحت پوشش
                  </p>
                </div>
              </div>
            </div>

            {/* Product showcase (desktop) */}
            <div className="hidden lg:block relative h-[580px]">
              {heroProducts.length > 0 ? (
                <>
                  {/* Main large card */}
                  <Link
                    href={`/products/${heroProducts[0].slug}`}
                    className="absolute w-64 bg-white rounded-3xl overflow-hidden shadow-[0_18px_40px_-12px_rgba(80,7,36,0.45),0_4px_12px_rgba(80,7,36,0.18)] ring-1 ring-pink-900/10 hover:scale-[1.03] transition-transform duration-300 animate-float-slow" style={
                      { top: '40px', right: '30px', '--rot': '-5deg' } as React.CSSProperties
                    }
                  >
                    <div className="aspect-square bg-pink-50">
                      {heroProducts[0].primary_image && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={heroProducts[0].primary_image}
                          alt={heroProducts[0].name_fa}
                          className="w-full h-full object-cover"
                        />
                      )}
                    </div>
                    <div className="p-4">
                      <p className="text-[10px] text-pink-600 uppercase font-bold tracking-wider">
                        {heroProducts[0].brand.name}
                      </p>
                      <p className="text-sm font-bold text-gray-900 mt-1 line-clamp-2">
                        {heroProducts[0].name_fa}
                      </p>
                      {heroProducts[0].min_price && (
                        <p className="text-sm font-bold text-pink-900 mt-2">
                          از {heroProducts[0].min_price.toLocaleString('fa-IR')}{' '}
                          تومان
                        </p>
                      )}
                    </div>
                  </Link>

                  {/* Second card */}
                  {heroProducts[1] && (
                    <Link
                      href={`/products/${heroProducts[1].slug}`}
                      className="absolute w-48 bg-white rounded-2xl overflow-hidden shadow-[0_14px_30px_-10px_rgba(80,7,36,0.45),0_3px_10px_rgba(80,7,36,0.18)] ring-1 ring-pink-900/10 hover:scale-[1.04] transition-transform duration-300 animate-float-slow" style={
                        {
                          top: '240px',
                          right: '0px',
                          '--rot': '4deg',
                          animationDelay: '1s',
                        } as React.CSSProperties
                      }
                    >
                      <div className="aspect-square bg-pink-50">
                        {heroProducts[1].primary_image && (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={heroProducts[1].primary_image}
                            alt={heroProducts[1].name_fa}
                            className="w-full h-full object-cover"
                          />
                        )}
                      </div>
                      <div className="p-3">
                        <p className="text-[10px] text-pink-600 uppercase font-bold">
                          {heroProducts[1].brand.name}
                        </p>
                        <p className="text-xs font-bold text-gray-900 mt-1 line-clamp-2">
                          {heroProducts[1].name_fa}
                        </p>
                      </div>
                    </Link>
                  )}

                  {/* Third card */}
                  {heroProducts[2] && (
                    <Link
                      href={`/products/${heroProducts[2].slug}`}
                      className="absolute w-44 bg-white rounded-2xl overflow-hidden shadow-[0_12px_26px_-10px_rgba(80,7,36,0.45),0_3px_9px_rgba(80,7,36,0.18)] ring-1 ring-pink-900/10 hover:scale-[1.04] transition-transform duration-300 animate-float-slow" style={
                        {
                          top: '400px',
                          right: '140px',
                          '--rot': '-2deg',
                          animationDelay: '2s',
                        } as React.CSSProperties
                      }
                    >
                      <div className="aspect-square bg-pink-50">
                        {heroProducts[2].primary_image && (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={heroProducts[2].primary_image}
                            alt={heroProducts[2].name_fa}
                            className="w-full h-full object-cover"
                          />
                        )}
                      </div>
                      <div className="p-3">
                        <p className="text-[10px] text-pink-600 uppercase font-bold">
                          {heroProducts[2].brand.name}
                        </p>
                        <p className="text-xs font-bold text-gray-900 mt-1 line-clamp-2">
                          {heroProducts[2].name_fa}
                        </p>
                      </div>
                    </Link>
                  )}

                  {/* Decorative badge */}
                  <div
                    className="absolute bg-white/15 backdrop-blur-md border border-white/25 rounded-2xl px-4 py-3 shadow-xl"
                    style={{ top: '120px', right: '310px' }}
                  >
                    <p className="text-[10px] text-pink-100 mb-1">
                      ارسال رایگان
                    </p>
                    <p className="text-sm font-bold text-white">بالای ۴ میلیون</p>
                  </div>

                  <div
                    className="absolute bg-pink-950/45 backdrop-blur-md border border-white/30 rounded-2xl px-4 py-3 shadow-xl"
                    style={{ top: '340px', right: '-40px' }}
                  >
                    <p className="text-[10px] text-pink-100 mb-1">
                      مجوز فروش
                    </p>
                    <p className="text-sm font-bold text-white">وزارت بهداشت</p>
                  </div>
                </>
              ) : (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-72 h-72 rounded-3xl bg-white/10 backdrop-blur-sm border-2 border-white/20 flex items-center justify-center animate-gentle-pulse">
                    <span className="text-8xl">💪</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ===== TRUST BAR (upgraded) ===== */}
      <section className="container mx-auto px-4 py-5 md:py-7">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
            <TrustItem
              icon={<ShieldIcon />}
              title="اصالت کالا"
              sub="دارای مجوز بهداشت"
            />
            <TrustItem
              icon={<TruckIcon />}
              title="ارسال سراسری"
              sub="به تمام نقاط ایران"
            />
            <TrustItem
              icon={<AwardIcon />}
              title="تضمین کیفیت"
              sub="کد رهگیری اصالت"
            />
            <TrustItem
              icon={<ChatIcon />}
              title="مشاوره تخصصی"
              sub="رایگان توسط کارشناس"
            />
        </div>
      </section>

      {/* ===== CATEGORIES ===== */}
      {data.categories.length > 0 && (
        <section className="container mx-auto px-4 py-6 md:py-8">
          <div className="rounded-3xl border border-pink-300/90 bg-[#f8d8e6] shadow-[0_10px_30px_rgba(131,24,67,0.12)] px-4 md:px-7 py-8 md:py-10">
          <div className="flex items-end justify-between mb-8">
            <div>
              <p className="section-label">دسته‌بندی</p>
              <h2 className="text-2xl md:text-3xl font-extrabold text-pink-950">
                خرید بر اساس دسته
              </h2>
            </div>
            <Link
              href="/products"
              className="group-link text-sm font-semibold text-pink-800 hover:text-pink-900 flex items-center gap-1"
            >
              مشاهده همه
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="arrow-slide"
              >
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </Link>
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-3 md:gap-4">
            {data.categories.map((cat) => (
              <Link
                key={cat.id}
                href={`/products?category=${cat.slug}`}
                className="group relative bg-white rounded-2xl p-3 text-center border border-pink-100/80 shadow-[var(--shadow-card)] hover:shadow-[var(--shadow-hover)] hover:border-pink-200 hover:-translate-y-1 transition-all duration-300 overflow-hidden"
              >
                {/* Pink gradient overlay on hover */}
                <div className="absolute inset-0 bg-gradient-to-br from-pink-100 via-pink-50 to-pink-200 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

                <div className="relative">
                  <div className="w-full aspect-square mx-auto mb-3 rounded-xl overflow-hidden bg-gradient-to-br from-pink-50 to-pink-100 flex items-center justify-center border border-pink-100/60 group-hover:border-pink-200 transition-colors">
                    {cat.image_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={cat.image_url}
                        alt={cat.name}
                        className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500"
                      />
                    ) : (
                      <span className="text-3xl group-hover:scale-110 transition-transform duration-300 select-none">
                        {getCategoryIcon(cat.slug)}
                      </span>
                    )}
                  </div>
                  <p className="text-xs md:text-sm font-bold text-gray-900 group-hover:text-pink-950 line-clamp-1 transition-colors">
                    {cat.name}
                  </p>
                </div>
              </Link>
            ))}
          </div>
          </div>
        </section>
      )}

      {/* ===== BESTSELLERS ===== */}
      {data.bestsellers.length > 0 && (
        <ProductSection
          label="محبوب مشتریان"
          title="پرفروش‌ترین‌ها"
          products={data.bestsellers}
        />
      )}

      {/* ===== PROMO BANNER ===== */}
      <section className="container mx-auto px-4 py-6">
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-pink-900 via-pink-800 to-pink-950 text-white p-8 md:p-14">
          {/* Layered background */}
          <div className="absolute inset-0 pointer-events-none">
            <div className="absolute -top-24 -left-24 w-72 h-72 rounded-full bg-pink-500/25 blur-3xl" />
            <div className="absolute -bottom-24 -right-24 w-80 h-80 rounded-full bg-pink-400/20 blur-3xl" />
            <div
              className="absolute inset-0 opacity-20"
              style={{
                backgroundImage:
                  'repeating-linear-gradient(45deg, transparent, transparent 20px, rgba(255,255,255,0.04) 20px, rgba(255,255,255,0.04) 22px)',
              }}
            />
          </div>

          <div className="relative grid md:grid-cols-2 gap-8 items-center">
            <div>
              <p className="text-[11px] font-bold tracking-widest uppercase text-pink-200 mb-2">
                فرصت محدود
              </p>
              <h2 className="text-3xl md:text-4xl font-black mb-3 leading-tight">
                ارسال رایگان
                <br />
                <span className="text-pink-200">
                  برای خرید بالای ۴ میلیون
                </span>
              </h2>
              <p className="text-sm md:text-base text-pink-100/90 mb-6">
                با هر خرید بالای ۴ میلیون تومان، ارسال به سراسر ایران کاملاً
                رایگان است.
              </p>
              <Link
                href="/products"
                className="group inline-flex items-center gap-2 bg-white text-pink-900 hover:bg-pink-100 font-bold px-6 py-3 rounded-xl transition-colors"
              >
                همین حالا خرید کنید
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="transition-transform group-hover:-translate-x-1"
                >
                  <path d="M15 18l-6-6 6-6" />
                </svg>
              </Link>
            </div>

            {/* Truck illustration */}
            <div className="hidden md:flex items-center justify-center relative">
              {/* Road line */}
              <div className="absolute bottom-12 left-0 right-0 h-0.5 bg-pink-400/30 rounded" />
              <div className="absolute bottom-14 left-10 w-8 h-0.5 bg-pink-200/50 rounded" />
              <div className="absolute bottom-14 right-20 w-6 h-0.5 bg-pink-200/50 rounded" />

              {/* Truck SVG */}
              <svg
                width="220"
                height="160"
                viewBox="0 0 24 24"
                fill="none"
                stroke="rgba(255,255,255,0.85)"
                strokeWidth="0.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="relative z-10 drop-shadow-2xl"
              >
                <rect x="1" y="3" width="15" height="13" />
                <polygon points="16 8 20 8 23 11 23 16 16 16 16 8" />
                <circle cx="5.5" cy="18.5" r="2.5" />
                <circle cx="18.5" cy="18.5" r="2.5" />
              </svg>

              {/* Speed lines */}
              <div className="absolute right-2 top-1/2 space-y-2 opacity-40">
                <div className="w-12 h-0.5 bg-pink-300 rounded" />
                <div className="w-8 h-0.5 bg-pink-300 rounded ml-4" />
                <div className="w-10 h-0.5 bg-pink-300 rounded ml-2" />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== NEW PRODUCTS ===== */}
      {data.new_products.length > 0 && (
        <ProductSection
          label="تازه رسیده"
          title="جدیدترین محصولات"
          products={data.new_products}
        />
      )}

      {/* ===== BRANDS ===== */}
      {data.brands.length > 0 && (
        <section className="py-8 md:py-10">
          <div className="container mx-auto px-4">
          <div className="text-center mb-8">
            <p className="section-label">برندها</p>
            <h2 className="text-2xl md:text-3xl font-extrabold text-pink-950">
              برندهای معتبر جهانی
            </h2>
          </div>
          <div className="flex flex-wrap justify-center gap-3">
            {data.brands.map((brand) => {
              const logoUrl = toAbsoluteUrl(brand.logo);
              return (
                <Link
                  key={brand.id}
                  href={`/products?brand=${brand.slug}`}
                  className="w-[calc(33.333%-0.5rem)] sm:w-[calc(25%-0.75rem)] md:w-[calc(16.666%-0.75rem)] max-w-[180px] bg-white rounded-xl p-4 border border-pink-100/80 shadow-[var(--shadow-card)] hover:shadow-[var(--shadow-hover)] hover:border-pink-200 transition-all group flex items-center justify-center aspect-[3/2] hover:-translate-y-0.5 hover:animate-brand-bob"
                >
                  {logoUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={logoUrl}
                      alt={brand.name}
                      className="max-h-12 max-w-full object-contain opacity-70 group-hover:opacity-100 transition-opacity"
                    />
                  ) : (
                    <span className="font-bold text-gray-600 text-xs md:text-sm text-center group-hover:text-pink-800 transition-colors">
                      {brand.name}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
          </div>
        </section>
      )}

      {/* ===== TESTIMONIALS ===== */}
      {data.testimonials.length > 0 && (
        <section className="py-10 md:py-14">
          <div className="container mx-auto px-4">
            <div className="text-center mb-10">
              <p className="section-label">نظرات مشتریان</p>
              <h2 className="text-2xl md:text-3xl font-extrabold text-pink-950">
                ورزشکاران درباره ما چه می‌گویند
              </h2>
            </div>
            <TestimonialsSlider testimonials={data.testimonials} />
          </div>
        </section>
      )}

      {/* Instagram CTA removed - will move to footer in batch D */}
    </div>
  );
}

/* ==================== HELPER COMPONENTS ==================== */

function TrustItem({
  icon,
  title,
  sub,
}: {
  icon: React.ReactNode;
  title: string;
  sub: string;
}) {
  return (
    <div className="group flex items-center gap-3 p-2 rounded-xl hover:bg-pink-50/70 transition-colors cursor-default">
      <div className="w-14 h-14 rounded-2xl bg-pink-50 border border-pink-200 group-hover:bg-pink-100 group-hover:border-pink-300 group-hover:scale-105 transition-all flex items-center justify-center text-pink-800 flex-shrink-0">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-sm md:text-base font-bold text-gray-900">{title}</p>
        <p className="text-[11px] md:text-xs text-gray-600 truncate">{sub}</p>
      </div>
    </div>
  );
}

function ShieldIcon() {
  return (
    <svg
      width="26"
      height="26"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

function TruckIcon() {
  return (
    <svg
      width="26"
      height="26"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="1" y="3" width="15" height="13" />
      <polygon points="16 8 20 8 23 11 23 16 16 16 16 8" />
      <circle cx="5.5" cy="18.5" r="2.5" />
      <circle cx="18.5" cy="18.5" r="2.5" />
    </svg>
  );
}

function AwardIcon() {
  return (
    <svg
      width="26"
      height="26"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="8" r="6" />
      <path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11" />
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg
      width="26"
      height="26"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function ProductSection({
  label,
  title,
  products,
}: {
  label: string;
  title: string;
  products: Product[];
}) {
  return (
    <section className="container mx-auto px-4 py-6 md:py-8">
      <div className="rounded-3xl border border-pink-300/90 bg-[#f5c2d8] shadow-[0_10px_30px_rgba(131,24,67,0.14)] px-4 md:px-7 py-8 md:py-10">
      <div className="flex items-end justify-between mb-8">
        <div>
          <p className="section-label">{label}</p>
          <h2 className="text-2xl md:text-3xl font-extrabold text-pink-950">
            {title}
          </h2>
        </div>
        <Link
          href="/products"
          className="group-link text-sm font-semibold text-pink-800 hover:text-pink-900 flex items-center gap-1"
        >
          مشاهده همه
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="arrow-slide"
          >
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </Link>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 md:gap-5">
        {products.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
      </div>
    </section>
  );
}

function ProductCard({ product }: { product: Product }) {
  return (
    <Link
      href={`/products/${product.slug}`}
      className="group bg-white rounded-2xl overflow-hidden border-2 border-pink-100 shadow-[var(--shadow-card)] hover:shadow-[var(--shadow-hover)] hover:border-pink-300 transition-all duration-300 hover:-translate-y-1"
    >
      <div className="aspect-square bg-gradient-to-br from-pink-50 via-pink-50 to-pink-100/60 overflow-hidden relative">
        {product.primary_image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={product.primary_image}
            alt={product.name_fa}
            className="w-full h-full object-cover group-hover:scale-[1.06] transition-transform duration-500"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-pink-300 text-sm">
            بدون عکس
          </div>
        )}
        {product.requires_cold_shipping && (
          <span className="absolute top-2 left-2 bg-blue-600 text-white text-[10px] font-bold px-2 py-1 rounded-full shadow">
            ❄ ارسال سرد
          </span>
        )}
      </div>
      <div className="p-3.5">
        <p className="brand-label">{product.brand.name}</p>
        <h3 className="font-bold text-gray-900 text-sm leading-relaxed line-clamp-2 mt-1 mb-2 min-h-[2.5rem]">
          {product.name_fa}
        </h3>
        <div className="pt-2 border-t border-pink-100/70">
          {product.min_price ? (
            <>
              <p className="text-[10px] text-gray-500 mb-0.5">شروع از</p>
              <p className="price-display text-base">
                {product.min_price.toLocaleString('fa-IR')}
                <span className="text-xs font-semibold text-gray-600 mr-1">
                  تومان
                </span>
              </p>
            </>
          ) : (
            <p className="text-gray-400 text-sm font-medium">به زودی</p>
          )}
        </div>
      </div>
    </Link>
  );
}



function getCategoryIcon(slug: string): string {
  const map: Record<string, string> = {
    protein: '🥛',
    whey: '🥛',
    creatine: '⚡',
    amino: '💧',
    gainer: '💪',
    vitamin: '💊',
    multi: '💊',
    fat: '🔥',
    burn: '🔥',
    clothing: '👕',
    apparel: '👕',
    shaker: '🥤',
    bottle: '🥤',
    equipment: '🏋️',
    gym: '🏋️',
    food: '🍫',
    nutrition: '🍫',
    health: '🌿',
  };
  const lower = slug.toLowerCase();
  for (const [key, icon] of Object.entries(map)) {
    if (lower.includes(key)) return icon;
  }
  return '🛒';
}