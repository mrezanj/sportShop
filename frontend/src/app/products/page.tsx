export const instant = false;

import Link from 'next/link';
import { fetchProducts, fetchCategories } from '@/lib/api';

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<{
    category?: string;
    brand?: string;
    search?: string;
    goal?: string;
  }>;
}) {
  const params = await searchParams;

  const [data, categories] = await Promise.all([
    fetchProducts({
      category: params.category,
      brand: params.brand,
      search: params.search,
      consumptionGoal: params.goal,
    }),
    fetchCategories(),
  ]);

  const activeCategory = params.category
    ? categories.find((c) => c.slug === params.category)
    : null;

  const pageTitle = activeCategory
    ? activeCategory.name
    : params.search
      ? `نتایج جستجو: ${params.search}`
      : 'همه محصولات';

  const hasFilter = Boolean(params.category || params.brand || params.search || params.goal);

  return (
    <div className="min-h-screen bg-page">
      {/* Page header with strong gradient hero */}
      <div className="relative overflow-hidden border-b border-pink-200/60 bg-gradient-to-br from-pink-100 via-pink-50 to-white">
        <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-pink-300/40 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-32 -left-32 w-80 h-80 rounded-full bg-pink-400/25 blur-3xl pointer-events-none" />
        <div
          className="absolute inset-0 opacity-40 pointer-events-none"
          style={{
            backgroundImage:
              'radial-gradient(circle at 1px 1px, rgba(157, 23, 77, 0.08) 1px, transparent 0)',
            backgroundSize: '20px 20px',
          }}
        />

        <div className="container mx-auto px-4 py-14 relative">
          <p className="section-label">فروشگاه</p>
          <h1 className="text-4xl font-extrabold text-pink-950 mb-3">
            {pageTitle}
          </h1>
          <div className="flex items-center gap-3 text-sm text-gray-700">
            <span className="font-medium">
              {data.count.toLocaleString('fa-IR')} محصول
            </span>
            {hasFilter && (
              <>
                <span className="w-1 h-1 rounded-full bg-gray-400" />
                <Link
                  href="/products"
                  className="text-pink-700 hover:text-pink-900 font-semibold"
                >
                  حذف فیلتر
                </Link>
              </>
            )}
          </div>
        </div>
      </div>

      <main className="container mx-auto px-4 py-10">
        <form method="get" className="mb-6 flex flex-wrap items-end gap-3 rounded-xl border border-pink-100 bg-white p-4">
          {params.category && <input type="hidden" name="category" value={params.category} />}
          {params.brand && <input type="hidden" name="brand" value={params.brand} />}
          {params.search && <input type="hidden" name="search" value={params.search} />}
          <label className="flex min-w-[220px] flex-1 flex-col gap-2 text-sm font-medium text-gray-700">
            فیلتر بر اساس هدف مصرف
            <input name="goal" defaultValue={params.goal ?? ''} placeholder="مثلاً ریکاوری یا افزایش حجم" className="rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-pink-700" />
          </label>
          <button type="submit" className="rounded-lg bg-pink-800 px-5 py-2.5 font-semibold text-white hover:bg-pink-900">اعمال فیلتر</button>
          {params.goal && <Link href="/products" className="px-3 py-2.5 text-sm text-pink-700 hover:underline">پاک‌کردن هدف مصرف</Link>}
        </form>
        {data.results.length === 0 ? (
          <div className="text-center py-20 bg-white/60 backdrop-blur-sm rounded-2xl border border-pink-100/60">
            <div className="text-5xl mb-3">🔍</div>
            <p className="text-lg font-semibold text-gray-800 mb-2">
              محصولی پیدا نشد
            </p>
            <p className="text-sm text-gray-600 mb-6">
              با فیلترهای دیگری امتحان کنید.
            </p>
            {hasFilter && (
              <Link
                href="/products"
                className="inline-block bg-pink-800 hover:bg-pink-900 text-white font-semibold px-6 py-2.5 rounded-xl transition-colors"
              >
                مشاهده همه محصولات
              </Link>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 md:gap-5">
            {data.results.map((product) => (
              <Link
                key={product.id}
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
                  <h2 className="font-bold text-gray-900 text-sm leading-relaxed line-clamp-2 mt-1 mb-2 min-h-[2.5rem]">
                    {product.name_fa}
                  </h2>
                  <div className="pt-2 border-t border-pink-100/70">
                    {product.min_price ? (
                      <>
                        <p className="text-[10px] text-gray-500 mb-0.5">
                          شروع از
                        </p>
                        <p className="price-display text-base">
                          {product.min_price.toLocaleString('fa-IR')}
                          <span className="text-xs font-semibold text-gray-600 mr-1">
                            تومان
                          </span>
                        </p>
                      </>
                    ) : (
                      <p className="text-gray-400 text-sm font-medium">
                        به زودی
                      </p>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}