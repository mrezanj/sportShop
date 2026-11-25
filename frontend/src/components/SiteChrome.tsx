
import { fetchCategories } from '@/lib/api';
import Header from '@/components/Header';

export default async function SiteChrome() {
  const categories = await fetchCategories();

  return <Header categories={categories} />;
}
