'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { useAuth } from '@/context/AuthContext';

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const input = 'w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-pink-500';

type Product = { id:number; name_fa:string; slug:string };
type Variant = {
  id:number; flavor:string; weight:string; servings:number|null; size:string; color:string;
  attributes:Record<string,string|number|boolean>; sku:string; price:string; is_active:boolean;
  shipping_weight_grams:number|null; shipping_length_cm:string|null; shipping_width_cm:string|null;
  shipping_height_cm:string|null; requires_special_packaging:boolean; special_packaging_cost:string;
};
type ImageRow = {id:number;image_url:string;alt_text:string;is_primary:boolean;order:number};
type VariantForm = {
  flavor:string;weight:string;servings:string;size:string;color:string;attributes:string;
  sku:string;initial_price:string;shipping_weight_grams:string;shipping_length_cm:string;
  shipping_width_cm:string;shipping_height_cm:string;requires_special_packaging:boolean;
  special_packaging_cost:string;is_active:boolean;
};
const blankVariant:VariantForm = {
  flavor:'',weight:'',servings:'',size:'',color:'',attributes:'{}',sku:'',initial_price:'',
  shipping_weight_grams:'',shipping_length_cm:'',shipping_width_cm:'',shipping_height_cm:'',
  requires_special_packaging:false,special_packaging_cost:'0',is_active:true,
};

export default function CatalogAssetsPage() {
  const {token,user,loading} = useAuth();
  const [products,setProducts] = useState<Product[]>([]);
  const [productId,setProductId] = useState('');
  const [variants,setVariants] = useState<Variant[]>([]);
  const [images,setImages] = useState<ImageRow[]>([]);
  const [variantForm,setVariantForm] = useState<VariantForm>(blankVariant);
  const [editingVariant,setEditingVariant] = useState<number|null>(null);
  const [imageFile,setImageFile] = useState<File|null>(null);
  const [altText,setAltText] = useState('');
  const [imageOrder,setImageOrder] = useState('0');
  const [primary,setPrimary] = useState(false);
  const [editingImage,setEditingImage] = useState<number|null>(null);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [notice,setNotice] = useState('');

  const api = async (path:string,method='GET',body?:BodyInit, multipart=false) => {
    const response = await fetch(`${API_URL}/${path}`,{
      method,
      headers:{Authorization:`Token ${token}`,...(body&&!multipart?{'Content-Type':'application/json'}:{})},
      body,
    });
    const data = await response.json().catch(()=>null);
    if(!response.ok) throw new Error(data?.detail || Object.values(data||{}).flat().join(' ') || 'عملیات ناموفق بود');
    return data;
  };

  const loadProducts = async () => {
    if(!token) return;
    try {
      const rows = await api('management/products/');
      setProducts(rows);
      if(!productId && rows.length) setProductId(String(rows[0].id));
    } catch(e) { setError(e instanceof Error?e.message:'دریافت محصولات ناموفق بود'); }
  };
  const loadAssets = async (id=productId) => {
    if(!token || !id) {setVariants([]);setImages([]);return;}
    try {
      const [v,i] = await Promise.all([
        api(`management/products/${id}/variants/`),
        api(`management/products/${id}/images/`),
      ]);
      setVariants(v);setImages(i);
    } catch(e) {setError(e instanceof Error?e.message:'دریافت اطلاعات ناموفق بود');}
  };
  useEffect(()=>{void loadProducts();},[token]);
  useEffect(()=>{if(productId) void loadAssets(productId);},[token,productId]);

  const resetVariant = () => {setEditingVariant(null);setVariantForm(blankVariant);};
  const editVariant = (v:Variant) => {
    setEditingVariant(v.id);
    setVariantForm({
      flavor:v.flavor||'',weight:v.weight||'',servings:v.servings===null?'':String(v.servings),
      size:v.size||'',color:v.color||'',attributes:JSON.stringify(v.attributes||{},null,2),
      sku:v.sku,initial_price:'',shipping_weight_grams:v.shipping_weight_grams===null?'':String(v.shipping_weight_grams),
      shipping_length_cm:v.shipping_length_cm||'',shipping_width_cm:v.shipping_width_cm||'',
      shipping_height_cm:v.shipping_height_cm||'',requires_special_packaging:v.requires_special_packaging,
      special_packaging_cost:v.special_packaging_cost||'0',is_active:v.is_active,
    });
  };
  const saveVariant = async(e:FormEvent) => {
    e.preventDefault();if(!productId)return;
    let attributes:Record<string,string|number|boolean>;
    try {attributes=JSON.parse(variantForm.attributes||'{}');}
    catch {setError('ویژگی‌های سفارشی باید JSON معتبر باشند.');return;}
    if(!attributes || Array.isArray(attributes) || typeof attributes!=='object') {setError('ویژگی‌های سفارشی باید یک شیء JSON باشند.');return;}
    const payload = {
      flavor:variantForm.flavor,weight:variantForm.weight,
      servings:variantForm.servings?Number(variantForm.servings):null,
      size:variantForm.size,color:variantForm.color,attributes,
      ...(editingVariant?{}:{sku:variantForm.sku,initial_price:variantForm.initial_price}),
      shipping_weight_grams:variantForm.shipping_weight_grams?Number(variantForm.shipping_weight_grams):null,
      shipping_length_cm:variantForm.shipping_length_cm||null,
      shipping_width_cm:variantForm.shipping_width_cm||null,
      shipping_height_cm:variantForm.shipping_height_cm||null,
      requires_special_packaging:variantForm.requires_special_packaging,
      special_packaging_cost:variantForm.special_packaging_cost||'0',is_active:variantForm.is_active,
    };
    setBusy(true);setError('');setNotice('');
    try {
      await api(editingVariant? `management/variants/${editingVariant}/`:`management/products/${productId}/variants/`,
        editingVariant?'PATCH':'POST',JSON.stringify(payload));
      setNotice(editingVariant?'تنوع به‌روزرسانی شد.':'تنوع و SKU ایجاد شد؛ قیمت اولیه در تاریخچه ثبت شد.');
      resetVariant();await loadAssets();
    } catch(e) {setError(e instanceof Error?e.message:'ذخیره تنوع ناموفق بود');}
    finally {setBusy(false);}
  };

  const resetImage = () => {setEditingImage(null);setImageFile(null);setAltText('');setImageOrder('0');setPrimary(false);};
  const editImage = (image:ImageRow) => {setEditingImage(image.id);setImageFile(null);setAltText(image.alt_text);setImageOrder(String(image.order));setPrimary(image.is_primary);};
  const saveImage = async(e:FormEvent) => {
    e.preventDefault();if(!productId)return;
    if(!editingImage&&!imageFile){setError('یک تصویر انتخاب کنید.');return;}
    const data=new FormData();
    if(imageFile)data.append('image',imageFile);
    data.append('alt_text',altText);data.append('order',imageOrder);data.append('is_primary',String(primary));
    setBusy(true);setError('');setNotice('');
    try {
      await api(editingImage?`management/images/${editingImage}/`:`management/products/${productId}/images/`,
        editingImage?'PATCH':'POST',data,true);
      setNotice(editingImage?'اطلاعات تصویر ذخیره شد.':'تصویر به گالری اضافه شد.');
      resetImage();await loadAssets();
    } catch(e) {setError(e instanceof Error?e.message:'ذخیره تصویر ناموفق بود');}
    finally {setBusy(false);}
  };
  const deleteImage = async(id:number) => {
    if(!window.confirm('تصویر حذف شود؟ در صورت حذف تصویر اصلی، تصویر بعدی به‌عنوان اصلی انتخاب می‌شود.'))return;
    setError('');
    try {await api(`management/images/${id}/`,'DELETE');setNotice('تصویر حذف شد.');await loadAssets();}
    catch(e){setError(e instanceof Error?e.message:'حذف تصویر ناموفق بود');}
  };

  if(loading)return <main className="p-12 text-center">در حال بررسی دسترسی...</main>;
  if(!user||!token)return <main className="p-12 text-center">برای دسترسی وارد حساب شوید.</main>;
  if(!user.is_staff)return <main className="p-12 text-center text-amber-700">این صفحه فقط برای کارکنان است.</main>;

  return <main dir="rtl" className="min-h-screen bg-page py-8"><div className="mx-auto max-w-7xl space-y-6 px-4">
    <header><p className="section-label">مدیریت فروشگاه</p><h1 className="text-3xl font-bold text-pink-950">تنوع‌ها و گالری تصاویر</h1>
      <p className="mt-2 text-sm text-gray-600">قیمت فقط هنگام ایجاد SKU و از مسیر مجاز قیمت‌گذاری ثبت می‌شود؛ موجودی در این صفحه قابل تغییر نیست.</p>
      <a href="/admin/catalog" className="mt-3 inline-block rounded-xl border bg-white px-4 py-2 text-sm font-bold">بازگشت به مدیریت کاتالوگ</a>
    </header>
    {error&&<div role="alert" className="rounded-xl bg-red-50 p-3 text-red-800">{error}</div>}
    {notice&&<div role="status" className="rounded-xl bg-emerald-50 p-3 text-emerald-800">{notice}</div>}
    <section className="rounded-2xl border bg-white p-4">
      <label className="block space-y-2 text-sm font-bold">انتخاب محصول
        <select className={input} value={productId} onChange={e=>{setProductId(e.target.value);resetVariant();resetImage();}}><option value="">انتخاب کنید</option>{products.map(p=><option key={p.id} value={p.id}>{p.name_fa} — {p.slug}</option>)}</select>
      </label>
    </section>
    {productId&&<>
      <section className="grid gap-5 lg:grid-cols-2">
        <form onSubmit={saveVariant} className="space-y-3 rounded-2xl border bg-white p-5">
          <h2 className="text-xl font-bold">{editingVariant?'ویرایش مشخصات تنوع':'ایجاد تنوع و SKU جدید'}</h2>
          {!editingVariant&&<><label className="block space-y-1 text-sm">قیمت اولیه (تومان)<input required min="1" type="number" className={input} value={variantForm.initial_price} onChange={e=>setVariantForm({...variantForm,initial_price:e.target.value})}/></label>
          <label className="block space-y-1 text-sm">SKU (اختیاری؛ خالی = تولید خودکار)<input dir="ltr" className={input} value={variantForm.sku} onChange={e=>setVariantForm({...variantForm,sku:e.target.value})}/></label></>}
          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1 text-sm">طعم<input className={input} value={variantForm.flavor} onChange={e=>setVariantForm({...variantForm,flavor:e.target.value})}/></label>
            <label className="space-y-1 text-sm">وزن نمایشی<input className={input} value={variantForm.weight} onChange={e=>setVariantForm({...variantForm,weight:e.target.value})}/></label>
            <label className="space-y-1 text-sm">تعداد سروینگ<input type="number" min="1" className={input} value={variantForm.servings} onChange={e=>setVariantForm({...variantForm,servings:e.target.value})}/></label>
            <label className="space-y-1 text-sm">سایز<input className={input} value={variantForm.size} onChange={e=>setVariantForm({...variantForm,size:e.target.value})}/></label>
            <label className="space-y-1 text-sm">رنگ<input className={input} value={variantForm.color} onChange={e=>setVariantForm({...variantForm,color:e.target.value})}/></label>
            <label className="space-y-1 text-sm">وزن ارسال (گرم)<input type="number" min="1" className={input} value={variantForm.shipping_weight_grams} onChange={e=>setVariantForm({...variantForm,shipping_weight_grams:e.target.value})}/></label>
          </div>
          <label className="block space-y-1 text-sm">ویژگی‌های سفارشی (JSON)<textarea dir="ltr" rows={4} className={input+' font-mono'} value={variantForm.attributes} onChange={e=>setVariantForm({...variantForm,attributes:e.target.value})}/></label>
          <div className="grid grid-cols-3 gap-2">
            <label className="space-y-1 text-xs">طول (cm)<input type="number" step="0.01" min="0.01" className={input} value={variantForm.shipping_length_cm} onChange={e=>setVariantForm({...variantForm,shipping_length_cm:e.target.value})}/></label>
            <label className="space-y-1 text-xs">عرض (cm)<input type="number" step="0.01" min="0.01" className={input} value={variantForm.shipping_width_cm} onChange={e=>setVariantForm({...variantForm,shipping_width_cm:e.target.value})}/></label>
            <label className="space-y-1 text-xs">ارتفاع (cm)<input type="number" step="0.01" min="0.01" className={input} value={variantForm.shipping_height_cm} onChange={e=>setVariantForm({...variantForm,shipping_height_cm:e.target.value})}/></label>
          </div>
          <label className="block space-y-1 text-sm">هزینه بسته‌بندی ویژه (تومان)<input type="number" min="0" className={input} value={variantForm.special_packaging_cost} onChange={e=>setVariantForm({...variantForm,special_packaging_cost:e.target.value})}/></label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={variantForm.requires_special_packaging} onChange={e=>setVariantForm({...variantForm,requires_special_packaging:e.target.checked})}/>نیازمند بسته‌بندی ویژه</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={variantForm.is_active} onChange={e=>setVariantForm({...variantForm,is_active:e.target.checked})}/>فعال</label>
          <div className="flex gap-2"><button disabled={busy} className="rounded-xl bg-pink-800 px-4 py-2 font-bold text-white">ذخیره</button><button type="button" onClick={resetVariant} className="rounded-xl border px-4 py-2">پاک کردن</button></div>
        </form>
        <section className="rounded-2xl border bg-white p-4">
          <h2 className="mb-3 text-xl font-bold">تنوع‌های ثبت‌شده</h2><div className="overflow-x-auto"><table className="w-full min-w-[520px] text-sm"><thead><tr className="border-b text-right"><th className="p-2">SKU</th><th className="p-2">ویژگی‌ها</th><th className="p-2">قیمت</th><th className="p-2">وضعیت</th><th className="p-2">ویرایش</th></tr></thead><tbody>{variants.map(v=><tr key={v.id} className="border-b"><td className="p-2" dir="ltr">{v.sku}</td><td className="p-2">{[v.flavor,v.weight,v.servings?String(v.servings)+' سروینگ':'',v.size,v.color].filter(Boolean).join(' / ')}</td><td className="p-2">{Number(v.price).toLocaleString('fa-IR')}</td><td className="p-2">{v.is_active?'فعال':'غیرفعال'}</td><td className="p-2"><button onClick={()=>editVariant(v)} className="font-bold text-blue-700">ویرایش</button></td></tr>)}</tbody></table>{!variants.length&&<p className="py-5 text-center text-gray-500">هنوز تنوعی ثبت نشده است.</p>}</div>
          <p className="mt-3 text-xs leading-6 text-gray-500">قیمت در این فرم فقط هنگام ایجاد SKU به‌عنوان قیمت اولیه ثبت می‌شود. برای تغییر قیمت از پنل قیمت‌گذاری استفاده کنید. موجودی فقط از اسناد انبار تغییر می‌کند.</p>
        </section>
      </section>
      <section className="grid gap-5 lg:grid-cols-2">
        <form onSubmit={saveImage} className="space-y-3 rounded-2xl border bg-white p-5">
          <h2 className="text-xl font-bold">{editingImage?'ویرایش تصویر':'افزودن تصویر به گالری'}</h2>
          <label className="block space-y-1 text-sm">فایل تصویر<input type="file" accept="image/*" className={input} onChange={e=>setImageFile(e.target.files?.[0]||null)} required={!editingImage}/></label>
          <label className="block space-y-1 text-sm">متن جایگزین<input className={input} maxLength={200} value={altText} onChange={e=>setAltText(e.target.value)}/></label>
          <label className="block space-y-1 text-sm">ترتیب نمایش<input type="number" min="0" className={input} value={imageOrder} onChange={e=>setImageOrder(e.target.value)}/></label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={primary} onChange={e=>setPrimary(e.target.checked)}/>تصویر اصلی محصول</label>
          <div className="flex gap-2"><button disabled={busy} className="rounded-xl bg-pink-800 px-4 py-2 font-bold text-white">ذخیره تصویر</button><button type="button" onClick={resetImage} className="rounded-xl border px-4 py-2">پاک کردن</button></div>
          <p className="text-xs text-gray-500">حداکثر حجم هر تصویر ۵ مگابایت است. انتخاب تصویر اصلی، تصویر اصلی قبلی را جایگزین می‌کند.</p>
        </form>
        <section className="rounded-2xl border bg-white p-4"><h2 className="mb-3 text-xl font-bold">گالری تصاویر</h2>
          <div className="grid grid-cols-2 gap-3">{images.map(image=><article key={image.id} className="space-y-2 rounded-xl border p-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}<img src={image.image_url} alt={image.alt_text||'تصویر محصول'} className="h-36 w-full rounded-lg object-contain bg-gray-50"/>
            <p className="text-sm font-bold">{image.alt_text||'بدون متن جایگزین'}</p><p className="text-xs text-gray-500">ترتیب: {image.order} {image.is_primary?' • تصویر اصلی':''}</p>
            <div className="flex gap-3 text-sm"><button onClick={()=>editImage(image)} className="font-bold text-blue-700">ویرایش</button><button onClick={()=>void deleteImage(image.id)} className="font-bold text-red-700">حذف</button></div>
          </article>)}</div>{!images.length&&<p className="py-5 text-center text-gray-500">هنوز تصویری ثبت نشده است.</p>}
        </section>
      </section>
    </>}
  </div></main>;
}
