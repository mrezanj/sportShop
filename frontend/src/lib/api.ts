
const API_URL = process.env.NEXT_PUBLIC_API_URL;

export interface Brand {
  id: number;
  name: string;
  slug: string;
  logo: string | null;
  description?: string;
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
  consumption_goals?: string[];
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
  consumptionGoal?: string;
}): Promise<PaginatedResponse<Product>> {
  const url = new URL(`${API_URL}/products/`);
  if (params?.search) url.searchParams.set('search', params.search);
  if (params?.category) url.searchParams.set('category__slug', params.category);
  if (params?.brand) url.searchParams.set('brand__slug', params.brand);
  if (params?.page) url.searchParams.set('page', String(params.page));
  if (params?.consumptionGoal) url.searchParams.set('consumption_goal', params.consumptionGoal);

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
  attributes: Record<string, string | number | boolean>;
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
  contraindications: string;
  medical_advice: string;
  license_id: string;
  authenticity_code: string;
  license_details: string;
  consumption_goals: string[];
  requires_cold_shipping: boolean;
  minimum_age: number | null;
  images: ProductImage[];
  variants: ProductVariant[];
  created_at: string;
  updated_at: string;
}

export async function fetchBrandBySlug(slug: string): Promise<Brand> {
  const res = await fetch(`${API_URL}/brands/${slug}/`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Brand not found');
  return res.json();
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
  quote_token: string;
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
  discount_amount?: number;
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
  discount_amount: number;
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


export interface InventorySummary {
  sku_count: number;
  low_stock_count: number;
  physical_quantity: number;
  reserved_quantity: number;
  available_quantity: number;
  pending_review_count: number;
  pending_approval_count: number;
  can_manage_threshold: boolean;
  can_create_document: boolean;
  can_review_document: boolean;
  can_approve_document: boolean;
}

export interface InventoryStockRow {
  variant_id: number;
  sku: string;
  product_name: string;
  brand_name: string;
  physical: number;
  reserved: number;
  available: number;
  minimum_quantity: number;
  low_stock: boolean;
}

export interface InventoryDocumentRow {
  id: number;
  document_number: string;
  document_type: string;
  status: string;
  reference: string | null;
  reason: string;
  created_by_id: number | null;
  reviewed_by_id: number | null;
  created_by_username: string | null;
  reviewed_by_username: string | null;
  approved_by_username: string | null;
  item_count: number;
  created_at: string;
  updated_at: string;
}

export interface InventoryDocumentItem {
  id: number;
  variant_id: number;
  batch_id: number | null;
  sku: string;
  product_name: string;
  batch_number: string | null;
  batch_status: string | null;
  batch_expiration_date: string | null;
  new_batch_expiration_date: string | null;
  new_batch_number: string;
  quantity: number;
  direction: string;
  unit_cost: number | null;
  reason: string;
}

export interface InventoryDocumentDetail extends InventoryDocumentRow {
  items: InventoryDocumentItem[];
}

export interface InventoryDocumentLog {
  id: number;
  action: string;
  from_status: string;
  to_status: string;
  actor_type: string;
  actor_username: string | null;
  note: string;
  created_at: string;
}

async function inventoryRequest<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}/inventory/${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      Authorization: `Token ${token}`,
      ...init?.headers,
    },
    cache: 'no-store',
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message =
      data?.detail ||
      (typeof data === 'object' ? Object.values(data).flat().find((v) => typeof v === 'string') : null) ||
      'خطا در دریافت اطلاعات انبار.';
    throw new Error(String(message));
  }
  return data as T;
}

export function fetchInventorySummary(token: string) {
  return inventoryRequest<InventorySummary>('summary/', token);
}

export function fetchInventoryLowStock(token: string) {
  return inventoryRequest<{ count: number; results: InventoryStockRow[] }>('low-stock/', token);
}

export function fetchInventoryThresholds(token: string) {
  return inventoryRequest<InventoryStockRow[]>('thresholds/', token);
}

export function updateInventoryThreshold(token: string, variantId: number, minimumQuantity: number) {
  return inventoryRequest<{ variant_id: number; sku: string; minimum_quantity: number }>(
    `thresholds/${variantId}/`,
    token,
    { method: 'PUT', body: JSON.stringify({ minimum_quantity: minimumQuantity }) }
  );
}

export function fetchInventoryDocuments(
  token: string,
  params: { page?: number; status?: string; type?: string; search?: string } = {}
) {
  const query = new URLSearchParams();
  if (params.page) query.set('page', String(params.page));
  if (params.status) query.set('status', params.status);
  if (params.type) query.set('type', params.type);
  if (params.search) query.set('search', params.search);
  const suffix = query.size ? `?${query.toString()}` : '';
  return inventoryRequest<PaginatedResponse<InventoryDocumentRow>>(
    `documents/${suffix}`,
    token
  );
}

export function fetchInventoryDocumentDetail(token: string, documentId: number) {
  return inventoryRequest<InventoryDocumentDetail>(`documents/${documentId}/`, token);
}

export function fetchInventoryDocumentHistory(token: string, documentId: number) {
  return inventoryRequest<InventoryDocumentLog[]>(`documents/${documentId}/history/`, token);
}


export interface CreateInventoryDocumentPayload {
  document_number: string;
  document_type: string;
  reference?: string;
  reason?: string;
  notes?: string;
}

export interface AddInventoryDocumentItemPayload {
  variant: number;
  quantity: number;
  direction: 'inbound' | 'outbound';
  batch?: number | null;
  new_batch_number?: string;
  new_batch_expiration_date?: string | null;
  unit_cost?: number | null;
  reason?: string;
}

export async function createInventoryDocument(token: string, payload: CreateInventoryDocumentPayload) {
  return inventoryRequest<{ id: number; document_number: string; document_type: string; status: string }>(
    'documents/create/', token, { method: 'POST', body: JSON.stringify(payload) }
  );
}

export async function addInventoryDocumentItem(token: string, documentId: number, payload: AddInventoryDocumentItemPayload) {
  return inventoryRequest<{ id: number; document_id: number; variant_id: number; quantity: number; direction: string; batch_id: number | null }>(
    `documents/${documentId}/items/`, token, { method: 'POST', body: JSON.stringify(payload) }
  );
}

export async function removeInventoryDocumentItem(token: string, documentId: number, itemId: number) {
  return inventoryRequest<void>(
    `documents/${documentId}/items/${itemId}/`, token, { method: 'DELETE' }
  );
}

async function inventoryDocumentAction(token: string, documentId: number, action: 'submit' | 'review' | 'approve' | 'reject', note = '') {
  return inventoryRequest<{ id: number; document_number: string; status: string }>(
    `documents/${documentId}/${action}/`, token,
    { method: 'POST', body: JSON.stringify({ note }) }
  );
}

export function submitInventoryDocument(token: string, documentId: number) {
  return inventoryDocumentAction(token, documentId, 'submit');
}
export function reviewInventoryDocument(token: string, documentId: number, note = '') {
  return inventoryDocumentAction(token, documentId, 'review', note);
}
export function approveInventoryDocument(token: string, documentId: number, note = '') {
  return inventoryDocumentAction(token, documentId, 'approve', note);
}
export function rejectInventoryDocument(token: string, documentId: number, note: string) {
  return inventoryDocumentAction(token, documentId, 'reject', note);
}


export interface ProductPriceUpdateRow {
  sku: string;
  value: string | number;
}

export interface ProductPriceUpdateResult {
  success: boolean;
  updated_count: number;
  items: { sku: string; old_price: number; new_price: number }[];
}

export interface ProductPriceHistoryRow {
  id: number;
  sku: string;
  product_name: string;
  old_price: string | null;
  new_price: string;
  change_type: string;
  changed_by__username: string | null;
  note: string;
  created_at: string;
}

export async function bulkUpdateProductPrices(
  token: string,
  payload: {
    mode: 'fixed' | 'increase_percent' | 'decrease_percent';
    items: ProductPriceUpdateRow[];
    note?: string;
  }
): Promise<ProductPriceUpdateResult> {
  const res = await fetch(`${API_URL}/products/bulk-price-update/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${token}`,
    },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || data?.sku || data?.items || 'به‌روزرسانی قیمت انجام نشد.');
  return data;
}

export async function importProductPrices(
  token: string,
  file: File
): Promise<ProductPriceUpdateResult> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_URL}/products/import-prices/`, {
    method: 'POST',
    headers: { Authorization: `Token ${token}` },
    body: form,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || data?.file || data?.sku || 'ورود قیمت انجام نشد.');
  return data;
}

export async function fetchProductPriceHistory(
  token: string,
  sku = ''
): Promise<ProductPriceHistoryRow[]> {
  const url = new URL(`${API_URL}/products/price-history/`);
  if (sku) url.searchParams.set('sku', sku);
  const res = await fetch(url.toString(), {
    headers: { Authorization: `Token ${token}` },
    cache: 'no-store',
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || 'دریافت سوابق قیمت انجام نشد.');
  return data;
}


export type DiscountScope = 'product' | 'category' | 'brand' | 'cart';
export type DiscountType = 'percent' | 'fixed';

export interface DiscountCampaign {
  id: number;
  name: string;
  code: string | null;
  scope: DiscountScope;
  product: number | null;
  category: number | null;
  brand: number | null;
  discount_type: DiscountType;
  value: string;
  maximum_discount_amount: string | null;
  minimum_order_amount: string;
  starts_at: string;
  ends_at: string;
  priority: number;
  is_stackable: boolean;
  first_purchase_only: boolean;
  max_uses: number | null;
  per_user_limit: number | null;
  usage_count: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type DiscountCampaignPayload = Omit<
  DiscountCampaign,
  'id' | 'usage_count' | 'created_at' | 'updated_at'
>;

async function discountApiRequest<T>(
  token: string,
  path: string,
  method = 'GET',
  payload?: unknown
): Promise<T> {
  const res = await fetch(`${API_URL}/${path}`, {
    method,
    headers: {
      Authorization: `Token ${token}`,
      ...(payload ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(payload ? { body: JSON.stringify(payload) } : {}),
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message =
      data?.detail ||
      data?.code?.[0] ||
      data?.name?.[0] ||
      data?.value?.[0] ||
      'عملیات مدیریت تخفیف انجام نشد.';
    throw new Error(message);
  }
  return data as T;
}

export function fetchDiscountCampaigns(token: string): Promise<DiscountCampaign[]> {
  return discountApiRequest<DiscountCampaign[]>(token, 'discounts/');
}

export function createDiscountCampaign(
  token: string,
  payload: DiscountCampaignPayload
): Promise<DiscountCampaign> {
  return discountApiRequest<DiscountCampaign>(token, 'discounts/', 'POST', payload);
}

export function updateDiscountCampaign(
  token: string,
  id: number,
  payload: Partial<DiscountCampaignPayload>
): Promise<DiscountCampaign> {
  return discountApiRequest<DiscountCampaign>(token, `discounts/${id}/`, 'PATCH', payload);
}

export function deleteDiscountCampaign(token: string, id: number): Promise<void> {
  return discountApiRequest<void>(token, `discounts/${id}/`, 'DELETE');
}
