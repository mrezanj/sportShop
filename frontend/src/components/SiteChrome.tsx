
import { fetchCategories } from '@/lib/api';
import Header from '@/components/Header';
import Footer from '@/components/Footer';

export default async function SiteChrome() {
  const categories = await fetchCategories();

  return (
    <>
      <Header categories={categories} />
      <Footer categories={categories} />
    </>
  );
}
