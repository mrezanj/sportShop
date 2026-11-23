
const API_URL = process.env.NEXT_PUBLIC_API_URL;

export interface Brand {
  id: number;
  name: string;
  slug: string;
  logo: string | null;
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  image_url: string | null;
  parent?: number | null;
}

export interface Product {
  id: number;
  name_fa: string;
  name_en: string;
  slug: string;
  brand: Brand;
  category: Category;
  primary_image: string | null;
  min_price: number | null;
  requires_cold_shipping: boolean;
  minimum_age: number | null;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export async function fetchProducts(params?: {
  search?: string;
  category?: string;
  brand?: string;
  page?: number;
}): Promise<PaginatedResponse<Product>> {
  const url = new URL(`${API_URL}/products/`);
  if (params?.search) url.searchParams.set('search', params.search);
  if (params?.category) url.searchParams.set('category__slug', params.category);
  if (params?.brand) url.searchParams.set('brand__slug', params.brand);
  if (params?.page) url.searchParams.set('page', String(params.page));

  const res = await fetch(url.toString(), { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to fetch products');
  return res.json();
}

export interface ProductImage {
  id: number;
  image_url: string | null;
  alt_text: string;
  is_primary: boolean;
  order: number;
}

export interface ProductVariant {
  id: number;
  flavor: string;
  weight: string;
  servings: number | null;
  size: string;
  color: string;
  sku: string;
  price: number;
  stock: number;
  is_active: boolean;
}

export interface ProductDetail {
  id: number;
  name_fa: string;
  name_en: string;
  slug: string;
  brand: Brand;
  category: Category;
  description: string;
  ingredients: string;
  usage: string;
  warnings: string;
  requires_cold_shipping: boolean;
  minimum_age: number | null;
  images: ProductImage[];
  variants: ProductVariant[];
  created_at: string;
  updated_at: string;
}

export async function fetchProductBySlug(slug: string): Promise<ProductDetail> {
  const res = await fetch(`${API_URL}/products/${slug}/`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Product not found');
  return res.json();
}

export async function fetchSimilarProducts(
  categorySlug: string,
  excludeSlug: string,
  limit = 4
): Promise<Product[]> {
  const url = new URL(`${API_URL}/products/`);
  url.searchParams.set('category__slug', categorySlug);
  const res = await fetch(url.toString(), { cache: 'no-store' });
  if (!res.ok) return [];
  const data: PaginatedResponse<Product> = await res.json();
  return data.results.filter((p) => p.slug !== excludeSlug).slice(0, limit);
}

export async function fetchCategories(): Promise<Category[]> {
  try {
    const res = await fetch(`${API_URL}/categories/`, { cache: 'no-store' });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : (data.results ?? []);
  } catch {
    return [];
  }
}

export interface AuthUser {
  id: number;
  mobile: string | null;
  is_staff: boolean;
}

export async function requestOTP(
  mobile: string
): Promise<{ success: boolean; expires_in: number }> {
  const res = await fetch(`${API_URL}/auth/request-otp/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mobile }),
  });
  const data = await res.json();
  if (!res.ok) {
    const msg =
      data?.mobile?.[0] ||
      data?.detail ||
      'خطا در ارسال کد. لطفاً دوباره تلاش کنید.';
    throw new Error(msg);
  }
  return data;
}

export async function verifyOTP(
  mobile: string,
  code: string
): Promise<{ success: boolean; token: string; user: AuthUser }> {
  const res = await fetch(`${API_URL}/auth/verify-otp/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mobile, code }),
  });
  const data = await res.json();
  if (!res.ok) {
    const msg = data?.code?.[0] || data?.detail || 'کد وارد شده صحیح نیست.';
    throw new Error(msg);
  }
  return data;
}

export async function fetchMe(token: string): Promise<AuthUser> {
  const res = await fetch(`${API_URL}/auth/me/`, {
    headers: { Authorization: `Token ${token}` },
    cache: 'no-store',
  });
  if (!res.ok) throw new Error('Invalid token');
  return res.json();
}

export interface UserProfile {
  mobile: string;
  birth_date: string | null;
}

export async function fetchProfile(token: string): Promise<UserProfile> {
  const res = await fetch(`${API_URL}/auth/profile/`, {
    headers: { Authorization: `Token ${token}` },
    cache: 'no-store',
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(data?.detail || 'خطا در دریافت اطلاعات پروفایل.');
  }

  return data;
}

export async function updateProfile(
  birthDate: string,
  token: string
): Promise<UserProfile> {
  const res = await fetch(`${API_URL}/auth/profile/`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${token}`,
    },
    body: JSON.stringify({ birth_date: birthDate || null }),
  });

  const data = await res.json();

  if (!res.ok) {
    const message =
      data?.birth_date?.[0] ||
      data?.detail ||
      'خطا در به‌روزرسانی پروفایل.';
    throw new Error(message);
  }

  return data;
}

export interface Province {
  slug: string;
  name: string;
}

export interface City {
  code: string;
  name: string;
  county_name: string;
  district_name: string;
}

export interface ShippingMethod {
  id: number;
  name: string;
  slug: string;
  description: string;
  cost: number | null;
}

export interface CreateOrderPayload {
  items: { variant_id: number; quantity: number }[];
  shipping_method_slug: string;
  province: string;
  city_code: string;
  address: string;
  postal_code?: string;
  first_name: string;
  last_name: string;
  mobile: string;
  notes?: string;
}

export interface CreateOrderResponse {
  success: boolean;
  order_number: string;
  total_amount: number;
  subtotal: number;
  vat_amount: number;
  shipping_cost: number;
}

export async function fetchProvinces(): Promise<Province[]> {
  try {
    const res = await fetch(`${API_URL}/locations/provinces/`, {
      cache: 'no-store',
    });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function fetchCities(province: string): Promise<City[]> {
  if (!province) return [];

  try {
    const url = new URL(`${API_URL}/locations/cities/`);
    url.searchParams.set('province', province);

    const res = await fetch(url.toString(), { cache: 'no-store' });
    if (!res.ok) return [];

    return res.json();
  } catch {
    return [];
  }
}

export async function fetchShippingMethods(
  province: string,
  cityCode: string
): Promise<ShippingMethod[]> {
  if (!province || !cityCode) return [];

  try {
    const url = new URL(`${API_URL}/orders/shipping-methods/`);
    url.searchParams.set('province', province);
    url.searchParams.set('city_code', cityCode);

    const res = await fetch(url.toString(), { cache: 'no-store' });
    if (!res.ok) return [];

    return res.json();
  } catch {
    return [];
  }
}

export async function createOrder(
  payload: CreateOrderPayload,
  token: string
): Promise<CreateOrderResponse> {
  const res = await fetch(`${API_URL}/orders/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${token}`,
    },
    body: JSON.stringify(payload),
  });
  const data = await res.json();

  if (!res.ok) {
    let msg = 'خطا در ثبت سفارش.';
    if (data && typeof data === 'object') {
      for (const key of Object.keys(data)) {
        const val = data[key];
        if (Array.isArray(val) && val.length > 0) {
          msg = String(val[0]);
          break;
        }
        if (typeof val === 'string') {
          msg = val;
          break;
        }
      }
    }
    throw new Error(msg);
  }
  return data;
}

export interface OrderItemDetail {
  product_name: string;
  product_slug: string;
  brand_name: string;
  variant_label: string;
  image_url: string;
  price: number;
  quantity: number;
  subtotal: number;
}

export interface OrderDetail {
  id: number;
  order_number: string;
  status: string;
  status_display: string;
  first_name: string;
  last_name: string;
  mobile: string;
  province: string;
  province_display: string;
  city: string;
  address: string;
  postal_code: string;
  shipping_method_name: string;
  shipping_cost: number;
  packaging_cost: number;
  shipping_is_free: boolean;
  packaging_is_free: boolean;
  subtotal: number;
  vat_amount: number;
  total_amount: number;
  tracking_code: string;
  notes: string;
  items: OrderItemDetail[];
  created_at: string;
}

export async function fetchMyOrders(
  token: string,
  page = 1
): Promise<PaginatedResponse<OrderDetail>> {
  const res = await fetch(
    `${API_URL}/orders/my/?page=${page}`,
    {
      headers: { Authorization: `Token ${token}` },
      cache: 'no-store',
    }
  );
  if (!res.ok) throw new Error('Failed to fetch orders');
  return res.json();
}

export async function fetchOrderDetail(
  orderNumber: string,
  token: string
): Promise<OrderDetail> {
  const res = await fetch(`${API_URL}/orders/${orderNumber}/`, {
    headers: { Authorization: `Token ${token}` },
    cache: 'no-store',
  });
  if (!res.ok) throw new Error('Order not found');
  return res.json();
}

export interface InitiatePaymentResponse {
  success: boolean;
  payment_id: number;
  redirect_url: string;
}

export interface VerifyPaymentResponse {
  success: boolean;
  ref_id?: string;
  order_number?: string;
  already_paid?: boolean;
  message?: string;
}

export async function initiatePayment(
  orderNumber: string,
  token: string
): Promise<InitiatePaymentResponse> {
  const res = await fetch(`${API_URL}/payments/initiate/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${token}`,
    },
    body: JSON.stringify({ order_number: orderNumber }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'خطا در شروع پرداخت');
  return data;
}

export async function verifyPayment(
  orderNumber: string,
  status: string,
  authority: string,
  token: string
): Promise<VerifyPaymentResponse> {
  const res = await fetch(`${API_URL}/payments/verify/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${token}`,
    },
    body: JSON.stringify({ order_number: orderNumber, status, authority }),
  });
  return res.json();
}

export interface Testimonial {
  id: number;
  name: string;
  role: string;
  content: string;
  rating: number;
  avatar_url: string | null;
  created_at: string;
}

export interface HomepageData {
  bestsellers: Product[];
  new_products: Product[];
  categories: Category[];
  brands: Brand[];
  testimonials: Testimonial[];
}

export async function fetchHomepageData(): Promise<HomepageData> {
  const empty: HomepageData = {
    bestsellers: [],
    new_products: [],
    categories: [],
    brands: [],
    testimonials: [],
  };
  try {
    const res = await fetch(`${API_URL}/home/`, { cache: 'no-store' });
    if (!res.ok) return empty;
    return res.json();
  } catch {
    return empty;
  }
}

/** Turn relative media URLs (like /media/brands/x.png) into absolute URLs. */
export function toAbsoluteUrl(url: string | null): string | null {
  if (!url) return null;
  if (/^https?:\/\//.test(url)) return url;
  const base = (process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api')
    .replace(/\/api\/?$/, '');
  const path = url.startsWith('/') ? url : '/' + url;
  return `${base}${path}`;
}
