
import type { Metadata } from 'next';
import { Suspense } from 'react';
import './globals.css';
import { AuthProvider } from '@/context/AuthContext';
import { CartProvider } from '@/context/CartContext';
import SiteChrome from '@/components/SiteChrome';

export const metadata: Metadata = {
  title: 'فروشگاه ورزشی | مرجع تخصصی مکمل و پوشاک ورزشی',
  description:
    'مرجع تخصصی مکمل‌های ورزشی، پوشاک، تجهیزات باشگاهی و محصولات بدون قند',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fa" dir="rtl">
      <body className="antialiased">
        <AuthProvider>
          <CartProvider>
            <Suspense fallback={null}>
              <SiteChrome />
            </Suspense>

            <main className="min-h-[60vh]">{children}</main>
          </CartProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
