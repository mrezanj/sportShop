'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCart } from '@/context/CartContext';
import { useAuth } from '@/context/AuthContext';

const VAT_RATE = 0.10;
const FREE_SHIPPING_THRESHOLD = 4_000_000;

export default function CartPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const { items, totalItems, totalPrice, updateQuantity, removeItem, clearCart } =
    useCart();

  const vat = Math.round(totalPrice * VAT_RATE);
  const initialTotal = totalPrice + vat;

  const handleCheckout = () => {
    if (!isAuthenticated) {
      router.push('/login?returnTo=/checkout');
      return;
    }
    router.push('/checkout');
  };

  if (items.length === 0) {
    return (
      <div className="min-h-screen bg-page" dir="rtl">
        <div className="container mx-auto px-4 py-16 text-center">
          <div className="text-6xl mb-4">🛒</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            سبد خرید شما خالی است
          </h1>
          <p className="text-gray-600 mb-6">
            هنوز محصولی به سبد اضافه نکرده‌اید.
          </p>
          <Link
            href="/products"
            className="inline-block bg-pink-800 hover:bg-pink-900 text-white px-6 py-3 rounded-lg transition-colors"
          >
            مشاهده محصولات
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-page" dir="rtl">
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-pink-900">
            سبد خرید ({totalItems.toLocaleString('fa-IR')} کالا)
          </h1>
          <button
            onClick={clearCart}
            className="text-sm text-red-600 hover:text-red-800"
          >
            خالی کردن سبد
          </button>
        </div>

        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-3">
            {items.map((item) => (
              <div
                key={item.variantId}
                className="border border-gray-200 rounded-xl p-4 flex gap-4 bg-white"
              >
                <div className="w-24 h-24 bg-pink-50 rounded-lg overflow-hidden flex-shrink-0">
                  {item.imageUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={item.imageUrl}
                      alt={item.productName}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-pink-300 text-xs">
                      بدون عکس
                    </div>
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <Link
                    href={`/products/${item.productSlug}`}
                    className="font-semibold text-gray-900 hover:text-pink-800 line-clamp-2"
                  >
                    {item.productName}
                  </Link>
                  <p className="text-xs text-pink-600 mt-1">
                    {item.brandName}
                  </p>
                  {item.variantLabel && item.variantLabel !== 'پیش فرض' && (
                    <p className="text-xs text-gray-600 mt-1">
                      {item.variantLabel}
                    </p>
                  )}

                  <div className="flex items-center justify-between mt-3">
                    <div className="flex items-center border border-gray-200 rounded-lg bg-white">
                      <button
                        onClick={() =>
                          updateQuantity(item.variantId, item.quantity - 1)
                        }
                        className="w-8 h-8 hover:bg-gray-50 text-lg text-gray-800"
                      >
                        −
                      </button>
                      <span className="w-10 text-center text-sm font-medium text-gray-900">
                        {item.quantity.toLocaleString('fa-IR')}
                      </span>
                      <button
                        onClick={() =>
                          updateQuantity(item.variantId, item.quantity + 1)
                        }
                        disabled={item.quantity >= item.stock}
                        className="w-8 h-8 hover:bg-gray-50 text-lg text-gray-800 disabled:text-gray-300"
                      >
                        +
                      </button>
                    </div>

                    <div className="text-left">
                      <p className="font-bold text-pink-900">
                        {(item.price * item.quantity).toLocaleString('fa-IR')}{' '}
                        تومان
                      </p>
                      <button
                        onClick={() => removeItem(item.variantId)}
                        className="text-xs text-red-500 hover:text-red-700 mt-1"
                      >
                        حذف
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <aside className="bg-pink-50 rounded-xl p-6 h-fit sticky top-24">
            <h2 className="font-bold text-pink-900 mb-4">خلاصه سفارش</h2>

            <div className="space-y-3 text-sm">
              <div className="flex justify-between items-center">
                <span className="text-gray-700">جمع کالاها</span>
                <span className="font-semibold text-gray-900">
                  {totalPrice.toLocaleString('fa-IR')} تومان
                </span>
              </div>

              <div className="flex justify-between items-center">
                <span className="text-gray-700">مالیات (۱۰٪)</span>
                <span className="font-semibold text-gray-900">
                  {vat.toLocaleString('fa-IR')} تومان
                </span>
              </div>

              <div className="flex justify-between items-center">
                <span className="text-gray-700">هزینه ارسال</span>
                <span className="font-semibold text-gray-500 text-xs">
                  در مرحله پرداخت
                </span>
              </div>

              <div className="border-t border-pink-300 pt-3 flex justify-between items-center">
                <span className="font-bold text-gray-900">
                  مبلغ نهایی (بدون ارسال)
                </span>
                <span className="font-bold text-pink-900 text-lg">
                  {initialTotal.toLocaleString('fa-IR')} تومان
                </span>
              </div>

              <p className="text-xs text-gray-700 bg-white border border-pink-200 rounded-lg p-2 mt-2">
                💡 هزینه ارسال در مرحله پرداخت بر اساس استان و روش انتخابی شما
                محاسبه و به مبلغ بالا اضافه می‌شود.
              </p>

              {totalPrice >= FREE_SHIPPING_THRESHOLD && (
                <p className="text-xs text-green-700 bg-green-50 border border-green-200 rounded-lg p-2">
                  🎉 خرید شما مشمول ارسال رایگان است.
                </p>
              )}
            </div>

            <button
              onClick={handleCheckout}
              className="w-full mt-6 bg-pink-800 hover:bg-pink-900 text-white font-semibold py-3 rounded-lg transition-colors"
            >
              ادامه فرآیند خرید
            </button>

            {!isAuthenticated && (
              <p className="text-xs text-gray-600 text-center mt-3">
                برای تکمیل خرید باید وارد شوید.
              </p>
            )}

            <Link
              href="/products"
              className="block text-center text-sm text-pink-800 hover:text-pink-900 mt-3 font-medium"
            >
              ادامه خرید
            </Link>
          </aside>
        </div>
      </div>
    </div>
  );
}