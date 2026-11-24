
const API_URL = process.env.NEXT_PUBLIC_API_URL;

export interface ShippingPreviewPayload {
  items: {
    variant_id: number;
    quantity: number;
  }[];
  shipping_method_slug: string;
  province: string;
  city_code: string;
  discount_code?: string;
}

export interface ShippingPreviewResponse {
  success: boolean;
  quote_token: string;
  quote_expires_in: number;
  items: {
    variant_id: number;
    sku: string;
    product_name: string;
    quantity: number;
    unit_price: number;
    line_subtotal: number;
  }[];
  subtotal: number;
  discount_amount: number;
  discounted_subtotal: number;
  discounts: {
    campaign_id: number;
    name: string;
    code: string;
    scope: 'product' | 'category' | 'brand' | 'cart';
    discount_amount: number;
  }[];
  vat_amount: number;
  shipping_cost: number;
  packaging_cost: number;
  total_amount: number;
  shipping: {
    base_cost: number;
    additional_weight_cost: number;
    cold_shipping_cost: number;
    is_free: boolean;
    billable_weight_grams: number;
  };
  packaging: {
    raw_cost: number;
    is_free: boolean;
  };
}

function getErrorMessage(data: unknown): string {
  if (typeof data === 'string') return data;

  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>;

    for (const value of Object.values(record)) {
      if (typeof value === 'string') return value;

      if (Array.isArray(value) && value.length > 0) {
        return String(value[0]);
      }

      if (value && typeof value === 'object') {
        const nested = getErrorMessage(value);
        if (nested) return nested;
      }
    }

    if (typeof record.detail === 'string') {
      return record.detail;
    }
  }

  return 'محاسبه هزینه سفارش با خطا مواجه شد.';
}

export async function fetchShippingPreview(
  payload: ShippingPreviewPayload,
  token: string
): Promise<ShippingPreviewResponse> {
  const res = await fetch(`${API_URL}/orders/shipping-preview/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${token}`,
    },
    body: JSON.stringify(payload),
    cache: 'no-store',
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(getErrorMessage(data));
  }

  return data as ShippingPreviewResponse;
}
