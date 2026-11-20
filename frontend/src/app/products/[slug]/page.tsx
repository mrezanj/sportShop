export const instant = false;

import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  fetchProductBySlug,
  fetchSimilarProducts,
} from '@/lib/api';
import VariantSelector from '@/components/VariantSelector';
import ProductGallery from '@/components/ProductGallery';

export default async function ProductPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  let product;
  try {
    product = await fetchProductBySlug(slug);
  } catch {
    notFound();
  }

  const similar = await fetchSimilarProducts(
    product.category.slug,
    product.slug
  );

  const primaryImage =
    product.images.find((img) => img.is_primary) ?? product.images[0];

  return (
    <div className="min-h-screen bg-page" dir="rtl">
      <div className="container mx-auto px-4 py-6">
        {/* Breadcrumb */}
        <nav className="text-sm text-gray-500 mb-6">
          <Link href="/" className="hover:text-pink-800">خانه</Link>
          <span className="mx-2">/</span>
          <Link
            href={`/products?category=${product.category.slug}`}
            className="hover:text-pink-800"
          >
            {product.category.name}
          </Link>
          <span className="mx-2">/</span>
          <span className="text-gray-800">{product.name_fa}</span>
        </nav>

        <div className="grid md:grid-cols-2 gap-8">
          {/* Gallery */}
          <ProductGallery
            images={product.images}
            productName={product.name_fa}
          />

          {/* Info + Variants */}
          <div className="space-y-4">
            <div>
              <p className="text-pink-600 font-medium">{product.brand.name}</p>
              <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mt-1">
                {product.name_fa}
              </h1>
              {product.name_en && (
                <p className="text-sm text-gray-400 mt-1" dir="ltr">
                  {product.name_en}
                </p>
              )}
            </div>

            {product.requires_cold_shipping && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                ❄️ این محصول با بسته‌بندی و ارسال سرد ارسال می‌شود.
              </div>
            )}

            <VariantSelector
              variants={product.variants}
              product={product}
              primaryImageUrl={primaryImage?.image_url ?? null}
            />

            <div className="text-sm text-gray-500 border-t pt-4 space-y-1">
              <p>
                <span className="text-gray-700 font-medium">دسته‌بندی: </span>
                {product.category.name}
              </p>
              <p>
                <span className="text-gray-700 font-medium">گارانتی اصالت: </span>
                دارای مجوز بهداشت و فروش مکمل
              </p>
            </div>
          </div>
        </div>

        {/* Details */}
        <div className="mt-12 space-y-8">
          {product.description && (
            <section>
              <h2 className="text-xl font-bold text-pink-900 mb-3 border-r-4 border-pink-800 pr-3">
                توضیحات
              </h2>
              <div className="text-gray-700 leading-relaxed whitespace-pre-line">
                {product.description}
              </div>
            </section>
          )}

          {product.ingredients && (
            <section>
              <h2 className="text-xl font-bold text-pink-900 mb-3 border-r-4 border-pink-800 pr-3">
                مواد تشکیل‌دهنده
              </h2>
              <p className="text-gray-700 leading-relaxed whitespace-pre-line">
                {product.ingredients}
              </p>
            </section>
          )}

          {product.usage && (
            <section>
              <h2 className="text-xl font-bold text-pink-900 mb-3 border-r-4 border-pink-800 pr-3">
                روش مصرف
              </h2>
              <p className="text-gray-700 leading-relaxed whitespace-pre-line">
                {product.usage}
              </p>
            </section>
          )}

          {product.warnings && (
            <section className="bg-red-50 border border-red-200 rounded-xl p-4">
              <h2 className="text-lg font-bold text-red-800 mb-2">
                ⚠️ هشدارها و منع مصرف
              </h2>
              <p className="text-red-900 leading-relaxed whitespace-pre-line">
                {product.warnings}
              </p>
              <p className="text-xs text-red-700 mt-3">
                فروش به افراد زیر ۱۸ سال محدود است. مصرف مکمل‌ها بدون
                توصیه پزشک یا متخصص تغذیه توصیه نمی‌شود.
              </p>
            </section>
          )}
        </div>

        {/* Similar Products */}
        {similar.length > 0 && (
          <div className="mt-16">
            <h2 className="text-xl font-bold text-pink-900 mb-6 border-r-4 border-pink-800 pr-3">
              محصولات مشابه
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {similar.map((p) => (
                <Link
                  key={p.id}
                  href={`/products/${p.slug}`}
                  className="group border border-gray-100 rounded-xl overflow-hidden hover:shadow-lg transition-shadow"
                >
                  <div className="aspect-square bg-pink-50 overflow-hidden">
                    {p.primary_image ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={p.primary_image}
                        alt={p.name_fa}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-pink-300 text-sm">
                        بدون عکس
                      </div>
                    )}
                  </div>
                  <div className="p-3">
                    <p className="text-xs text-pink-600 mb-1">{p.brand.name}</p>
                    <p className="text-sm font-medium text-gray-800 line-clamp-2">
                      {p.name_fa}
                    </p>
                    {p.min_price && (
                      <p className="text-sm text-pink-900 font-bold mt-1">
                        {p.min_price.toLocaleString('fa-IR')} تومان
                      </p>
                    )}
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