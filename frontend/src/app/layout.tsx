
import type { Metadata } from 'next';
import { Suspense } from 'react';
import './globals.css';
import { AuthProvider } from '@/context/AuthContext';
import { CartProvider } from '@/context/CartContext';
import SiteChrome from '@/components/SiteChrome';
import SiteFooter from '@/components/SiteFooter';

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
      <body className="antialiased flex min-h-screen flex-col">
        <AuthProvider>
          <CartProvider>
            <Suspense fallback={null}>
              <SiteChrome />
            </Suspense>

            <div className="min-h-[60vh] flex-1">{children}</div>

            <Suspense fallback={null}>
              <SiteFooter />
            </Suspense>
          </CartProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
