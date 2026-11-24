export const instant = false;

import Link from 'next/link';
import { notFound } from 'next/navigation';
import { fetchProductBySlug, fetchSimilarProducts } from '@/lib/api';
import VariantSelector from '@/components/VariantSelector';
import ProductGallery from '@/components/ProductGallery';

function DetailSection({ title, children }: { title: string; children: string }) {
  if (!children?.trim()) return null;
  return (
    <section>
      <h2 className="text-xl font-bold text-pink-900 mb-3 border-r-4 border-pink-800 pr-3">{title}</h2>
      <p className="text-gray-700 leading-relaxed whitespace-pre-line">{children}</p>
    </section>
  );
}

export default async function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let product;
  try {
    product = await fetchProductBySlug(slug);
  } catch {
    notFound();
  }

  const similar = await fetchSimilarProducts(product.category.slug, product.slug);
  const primaryImage = product.images.find((img) => img.is_primary) ?? product.images[0];
  const activeVariants = product.variants.filter((variant) => variant.is_active);
  const availableVariants = activeVariants.filter((variant) => variant.stock > 0);

  return (
    <div className="min-h-screen bg-page" dir="rtl">
      <div className="container mx-auto px-4 py-6">
        <nav className="text-sm text-gray-500 mb-6">
          <Link href="/" className="hover:text-pink-800">خانه</Link>
          <span className="mx-2">/</span>
          <Link href={`/products?category=${product.category.slug}`} className="hover:text-pink-800">{product.category.name}</Link>
          <span className="mx-2">/</span>
          <span className="text-gray-800">{product.name_fa}</span>
        </nav>

        <div className="grid md:grid-cols-2 gap-8">
          <ProductGallery images={product.images} productName={product.name_fa} />
          <div className="space-y-4">
            <div>
              <Link href={`/brands/${product.brand.slug}`} className="text-pink-600 font-medium hover:underline">{product.brand.name}</Link>
              <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mt-1">{product.name_fa}</h1>
              {product.name_en && <p className="text-sm text-gray-400 mt-1" dir="ltr">{product.name_en}</p>}
            </div>

            {product.requires_cold_shipping && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">❄️ این محصول با بسته‌بندی و ارسال سرد ارسال می‌شود.</div>
            )}
            {product.minimum_age && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
                خرید این محصول برای افراد زیر {product.minimum_age.toLocaleString('fa-IR')} سال مجاز نیست.
              </div>
            )}
            {availableVariants.length > 0 ? (
              <VariantSelector variants={product.variants} product={product} primaryImageUrl={primaryImage?.image_url ?? null} />
            ) : (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-gray-700">
                <p className="font-semibold">این محصول در حال حاضر موجود نیست.</p>
                <p className="mt-1 text-sm">امکان ثبت سفارش یا پیش‌خرید محصول ناموجود وجود ندارد.</p>
              </div>
            )}

            <div className="text-sm text-gray-600 border-t pt-4 space-y-2">
              <p><span className="text-gray-800 font-medium">دسته‌بندی: </span>{product.category.name}</p>
              {product.license_id && <p><span className="text-gray-800 font-medium">شناسه مجوز: </span>{product.license_id}</p>}
              {product.authenticity_code && <p><span className="text-gray-800 font-medium">شناسه اصالت: </span>{product.authenticity_code}</p>}
              {product.license_details && <p className="whitespace-pre-line">{product.license_details}</p>}
            </div>
            {product.consumption_goals.length > 0 && (
              <div>
                <p className="font-semibold text-gray-800 mb-2">اهداف مصرف</p>
                <div className="flex flex-wrap gap-2">
                  {product.consumption_goals.map((goal) => <span key={goal} className="rounded-full bg-pink-50 text-pink-800 px-3 py-1 text-sm">{goal}</span>)}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="mt-12 space-y-8">
          <DetailSection title="توضیحات" children={product.description} />
          <DetailSection title="مواد تشکیل‌دهنده" children={product.ingredients} />
          <DetailSection title="روش مصرف" children={product.usage} />
          <DetailSection title="توصیه پزشکی" children={product.medical_advice} />
          <DetailSection title="موارد منع مصرف" children={product.contraindications} />
          {product.warnings && (
            <section className="bg-red-50 border border-red-200 rounded-xl p-4">
              <h2 className="text-lg font-bold text-red-800 mb-2">⚠️ هشدارهای مصرف</h2>
              <p className="text-red-900 leading-relaxed whitespace-pre-line">{product.warnings}</p>
            </section>
          )}
        </div>

        {similar.length > 0 && (
          <div className="mt-16">
            <h2 className="text-xl font-bold text-pink-900 mb-6 border-r-4 border-pink-800 pr-3">محصولات مشابه</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {similar.map((p) => (
                <Link key={p.id} href={`/products/${p.slug}`} className="group border border-gray-100 rounded-xl overflow-hidden hover:shadow-lg transition-shadow">
                  <div className="aspect-square bg-pink-50 overflow-hidden">
                    {p.primary_image ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={p.primary_image} alt={p.name_fa} className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
                    ) : <div className="w-full h-full flex items-center justify-center text-pink-300 text-sm">بدون عکس</div>}
                  </div>
                  <div className="p-3">
                    <p className="text-xs text-pink-600 mb-1">{p.brand.name}</p>
                    <p className="text-sm font-medium text-gray-800 line-clamp-2">{p.name_fa}</p>
                    {p.min_price !== null && <p className="text-sm text-pink-900 font-bold mt-1">{p.min_price.toLocaleString('fa-IR')} تومان</p>}
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
