import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/context/AuthContext';
import { CartProvider } from '@/context/CartContext';
import Header from '@/components/Header';
import Footer from '@/components/Footer';
import { fetchCategories } from '@/lib/api';

export const metadata: Metadata = {
  title: 'فروشگاه ورزشی | مرجع تخصصی مکمل و پوشاک ورزشی',
  description:
    'مرجع تخصصی مکمل‌های ورزشی، پوشاک، تجهیزات باشگاهی و محصولات بدون قند',
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const categories = await fetchCategories();

  return (
    <html lang="fa" dir="rtl">
      <body className="antialiased">
        <AuthProvider>
          <CartProvider>
            <Header categories={categories} />
            <main className="min-h-[60vh]">{children}</main>
            <Footer categories={categories} />
          </CartProvider>
        </AuthProvider>
      </body>
    </html>
  );
}