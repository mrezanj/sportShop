import { fetchCategories } from '@/lib/api';
import Footer from '@/components/Footer';

export default async function SiteFooter() {
  const categories = await fetchCategories();

  return <Footer categories={categories} />;
}
