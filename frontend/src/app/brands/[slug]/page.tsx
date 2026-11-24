export const instant = false;

import Link from 'next/link';
import { notFound } from 'next/navigation';
import { fetchBrandBySlug, fetchProducts } from '@/lib/api';

export default async function BrandPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let brand;
  try { brand = await fetchBrandBySlug(slug); } catch { notFound(); }
  const products = await fetchProducts({ brand: slug });
  return (
    <main className="min-h-screen bg-page" dir="rtl">
      <header className="border-b border-pink-100 bg-gradient-to-br from-pink-100 via-pink-50 to-white">
        <div className="container mx-auto px-4 py-12">
          <h1 className="text-3xl font-extrabold text-pink-950">{brand.name}</h1>
          {brand.description && <p className="mt-3 max-w-3xl leading-8 text-gray-700 whitespace-pre-line">{brand.description}</p>}
          <p className="mt-4 text-sm text-gray-600">{products.count.toLocaleString('fa-IR')} محصول</p>
        </div>
      </header>
      <section className="container mx-auto px-4 py-10">
        {products.results.length === 0 ? <p className="rounded-xl border border-pink-100 bg-white p-8 text-center text-gray-600">در حال حاضر محصول فعالی برای این برند ثبت نشده است.</p> : (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
            {products.results.map((product) => (
              <Link key={product.id} href={`/products/${product.slug}`} className="overflow-hidden rounded-xl border border-pink-100 bg-white transition hover:-translate-y-1 hover:shadow-lg">
                <div className="aspect-square bg-pink-50">
                  {product.primary_image ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={product.primary_image} alt={product.name_fa} className="h-full w-full object-cover" />
                  ) : <div className="flex h-full items-center justify-center text-sm text-pink-300">بدون عکس</div>}
                </div>
                <div className="p-3"><h2 className="line-clamp-2 text-sm font-semibold text-gray-900">{product.name_fa}</h2>
                  {product.min_price !== null ? <p className="mt-2 font-bold text-pink-900">{product.min_price.toLocaleString('fa-IR')} تومان</p> : <p className="mt-2 text-sm text-gray-400">به زودی</p>}
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
