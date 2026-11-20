'use client';

import { useState } from 'react';
import type { ProductVariant, ProductDetail } from '@/lib/api';
import { useCart } from '@/context/CartContext';

interface Props {
  variants: ProductVariant[];
  product: ProductDetail;
  primaryImageUrl: string | null;
}

export default function VariantSelector({
  variants,
  product,
  primaryImageUrl,
}: Props) {
  const activeVariants = variants.filter((v) => v.is_active);
  const [selectedId, setSelectedId] = useState<number | null>(
    activeVariants[0]?.id ?? null
  );
  const [message, setMessage] = useState<{
    type: 'success' | 'warning';
    text: string;
  } | null>(null);
  const { addItem, getQuantityInCart } = useCart();

  const selected = activeVariants.find((v) => v.id === selectedId) ?? null;

  // Detect: single variant with no distinguishing attributes
  const isSingleSimpleVariant =
    activeVariants.length === 1 &&
    !activeVariants[0].flavor &&
    !activeVariants[0].weight &&
    !activeVariants[0].size &&
    !activeVariants[0].color;

  if (activeVariants.length === 0) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-center text-gray-500">
        این محصول فعلاً موجود نیست.
      </div>
    );
  }

  const handleAddToCart = () => {
    if (!selected || selected.stock === 0) return;

    const currentInCart = getQuantityInCart(selected.id);

    if (currentInCart >= selected.stock) {
      setMessage({
        type: 'warning',
        text: 'حداکثر موجودی این محصول در سبد شماست.',
      });
      setTimeout(() => setMessage(null), 2500);
      return;
    }

    // Label: empty string if no attributes, never "پیش‌فرض"
    const label = [
      selected.flavor,
      selected.weight,
      selected.size,
      selected.color,
    ]
      .filter(Boolean)
      .join(' - ');

    addItem({
      variantId: selected.id,
      productId: product.id,
      productSlug: product.slug,
      productName: product.name_fa,
      brandName: product.brand.name,
      imageUrl: primaryImageUrl,
      variantLabel: label,
      price: selected.price,
      stock: selected.stock,
    });

    setMessage({ type: 'success', text: '✓ به سبد اضافه شد' });
    setTimeout(() => setMessage(null), 2000);
  };

  const variantLabelOf = (variant: ProductVariant) =>
    [variant.flavor, variant.weight, variant.size, variant.color]
      .filter(Boolean)
      .join(' - ');

  return (
    <div className="space-y-4">
      {/* Variant selection (only when NOT a single simple variant) */}
      {!isSingleSimpleVariant && (
        <div>
          <h3 className="font-semibold text-gray-800 mb-2">انتخاب تنوع:</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {activeVariants.map((variant) => {
              const label = variantLabelOf(variant) || `تنوع ${variant.id}`;
              const isSelected = variant.id === selectedId;
              const isOutOfStock = variant.stock === 0;

              return (
                <button
                  key={variant.id}
                  onClick={() => setSelectedId(variant.id)}
                  disabled={isOutOfStock}
                  className={`text-sm border rounded-lg p-2 transition-colors ${
                    isSelected
                      ? 'border-pink-800 bg-pink-50 text-pink-900'
                      : isOutOfStock
                      ? 'border-gray-200 bg-gray-50 text-gray-400 cursor-not-allowed'
                      : 'border-gray-200 hover:border-pink-300'
                  }`}
                >
                  {label}
                  {isOutOfStock && (
                    <span className="block text-xs mt-1">ناموجود</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Price + Add to cart */}
      {selected && (
        <div className="bg-pink-50 rounded-lg p-4 space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-gray-600 text-sm">قیمت:</span>
            <span className="text-pink-900 font-bold text-lg">
              {selected.price.toLocaleString('fa-IR')} تومان
            </span>
          </div>
          <div className="flex justify-between items-center text-sm">
            <span className="text-gray-600">موجودی:</span>
            <span
              className={selected.stock > 0 ? 'text-green-700' : 'text-red-600'}
            >
              {selected.stock > 0
                ? `${selected.stock.toLocaleString('fa-IR')} عدد`
                : 'ناموجود'}
            </span>
          </div>
          <div className="flex justify-between items-center text-xs text-gray-500">
            <span>کد محصول:</span>
            <span dir="ltr">{selected.sku}</span>
          </div>

          <button
            disabled={selected.stock === 0}
            onClick={handleAddToCart}
            className={`w-full mt-2 font-semibold py-3 rounded-lg transition-colors ${
              message?.type === 'success'
                ? 'bg-green-600 text-white'
                : message?.type === 'warning'
                ? 'bg-amber-500 text-white'
                : 'bg-pink-800 hover:bg-pink-900 disabled:bg-gray-300 disabled:cursor-not-allowed text-white'
            }`}
          >
            {message?.text ??
              (selected.stock > 0 ? 'افزودن به سبد خرید' : 'ناموجود')}
          </button>

          {(() => {
            const inCart = getQuantityInCart(selected.id);
            if (inCart === 0) return null;
            return (
              <p className="text-xs text-gray-500 mt-2 text-center">
                {inCart.toLocaleString('fa-IR')} عدد در سبد شما
                {inCart >= selected.stock && ' (حداکثر)'}
              </p>
            );
          })()}
        </div>
      )}
    </div>
  );
}