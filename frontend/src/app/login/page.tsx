'use client';

import { Suspense, useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import { requestOTP, verifyOTP } from '@/lib/api';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnTo = searchParams.get('returnTo') || '/';
  const { loginWithToken, isAuthenticated } = useAuth();

  const [step, setStep] = useState<'mobile' | 'otp'>('mobile');
  const [mobile, setMobile] = useState('');
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(0);

  // اگر از قبل وارد شده، مستقیم برود به مقصد
  useEffect(() => {
    if (isAuthenticated) router.push(returnTo);
  }, [isAuthenticated, router, returnTo]);

  // شمارش معکوس
  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const handleRequestOTP = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!/^09\d{9}$/.test(mobile)) {
      setError('شماره موبایل معتبر نیست. (مثال: 09121234567)');
      return;
    }

    setLoading(true);
    try {
      await requestOTP(mobile);
      setStep('otp');
      setCountdown(120);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'خطای نامشخص');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOTP = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!/^\d{6}$/.test(code)) {
      setError('کد باید ۶ رقم باشد.');
      return;
    }

    setLoading(true);
    try {
      const data = await verifyOTP(mobile, code);
      loginWithToken(data.token, data.user);
      router.push(returnTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'خطای نامشخص');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setError(null);
    setLoading(true);
    try {
      await requestOTP(mobile);
      setCountdown(120);
      setCode('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'خطای نامشخص');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-white flex items-center justify-center px-4 py-12" dir="rtl">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <Link href="/" className="text-2xl font-bold text-pink-900">
            فروشگاه ورزشی
          </Link>
          <h1 className="text-xl font-semibold text-gray-800 mt-6">
            {step === 'mobile' ? 'ورود / ثبت‌نام' : 'تایید شماره موبایل'}
          </h1>
          <p className="text-sm text-gray-500 mt-2">
            {step === 'mobile'
              ? 'شماره موبایل خود را وارد کنید تا کد تایید برایتان ارسال شود.'
              : `کد ۶ رقمی ارسال شده به ${mobile} را وارد کنید.`}
          </p>
        </div>

        <div className="bg-white border border-pink-100 rounded-2xl p-6 shadow-sm">
          {step === 'mobile' ? (
            <form onSubmit={handleRequestOTP} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  شماره موبایل
                </label>
                <input
                  type="tel"
                  inputMode="numeric"
                  value={mobile}
                  onChange={(e) =>
                    setMobile(e.target.value.replace(/[^\d]/g, '').slice(0, 11))
                  }
                  placeholder="09121234567"
                  dir="ltr"
                  className="w-full border border-gray-300 rounded-lg px-4 py-3 text-center text-lg tracking-widest focus:outline-none focus:border-pink-800 text-gray-900"
                  autoFocus
                />
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading || mobile.length !== 11}
                className="w-full bg-pink-800 hover:bg-pink-900 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition-colors"
              >
                {loading ? 'در حال ارسال...' : 'دریافت کد تایید'}
              </button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOTP} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  کد تایید
                </label>
                <input
                  type="text"
                  inputMode="numeric"
                  value={code}
                  onChange={(e) =>
                    setCode(e.target.value.replace(/[^\d]/g, '').slice(0, 6))
                  }
                  placeholder="------"
                  dir="ltr"
                  className="w-full border border-gray-300 rounded-lg px-4 py-3 text-center text-2xl tracking-[0.5em] focus:outline-none focus:border-pink-800 text-gray-900"
                  autoFocus
                />
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading || code.length !== 6}
                className="w-full bg-pink-800 hover:bg-pink-900 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition-colors"
              >
                {loading ? 'در حال بررسی...' : 'تایید و ورود'}
              </button>

              <div className="flex justify-between items-center text-sm pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setStep('mobile');
                    setCode('');
                    setError(null);
                  }}
                  className="text-gray-600 hover:text-gray-800"
                >
                  تغییر شماره
                </button>

                {countdown > 0 ? (
                  <span className="text-gray-500">
                    ارسال مجدد تا {countdown} ثانیه
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={handleResend}
                    disabled={loading}
                    className="text-pink-800 hover:text-pink-900 font-medium"
                  >
                    ارسال مجدد کد
                  </button>
                )}
              </div>
            </form>
          )}
        </div>

        <p className="text-center text-xs text-gray-500 mt-6">
          با ورود،{' '}
          <span className="text-pink-700">قوانین و مقررات</span> و{' '}
          <span className="text-pink-700">حریم خصوصی</span> را می‌پذیرید.
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-gray-500">
          در حال بارگذاری...
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}