'use client';

import { useState, useRef, useEffect } from 'react';
import type { ProductImage } from '@/lib/api';

const ZOOM_LEVEL = 2.5;

interface Props {
  images: ProductImage[];
  productName: string;
}

export default function ProductGallery({ images, productName }: Props) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [animate, setAnimate] = useState(true);
  const dragRef = useRef({ startX: 0, startY: 0, origX: 0, origY: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  const isZoomed = zoom > 1;
  const currentImage = images?.[selectedIndex];
  const hasMultiple = images && images.length > 1;

  const getMaxPan = () => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return { maxX: 0, maxY: 0 };
    return {
      maxX: ((ZOOM_LEVEL - 1) / 2) * rect.width,
      maxY: ((ZOOM_LEVEL - 1) / 2) * rect.height,
    };
  };

  const resetZoom = () => {
    setAnimate(true);
    setZoom(1);
    setPosition({ x: 0, y: 0 });
  };

  const zoomAtPoint = (clientX: number, clientY: number) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;

    const clickX = clientX - rect.left;
    const clickY = clientY - rect.top;
    const { maxX, maxY } = getMaxPan();

    const rawX = -(clickX - rect.width / 2) * ZOOM_LEVEL;
    const rawY = -(clickY - rect.height / 2) * ZOOM_LEVEL;

    setAnimate(true);
    setZoom(ZOOM_LEVEL);
    setPosition({
      x: Math.max(-maxX, Math.min(maxX, rawX)),
      y: Math.max(-maxY, Math.min(maxY, rawY)),
    });
  };

  const handlePointerDown = (e: React.PointerEvent) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;

    if (!isZoomed) {
      zoomAtPoint(e.clientX, e.clientY);
      return;
    }

    e.preventDefault();
    setDragging(true);
    setAnimate(false);
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origX: position.x,
      origY: position.y,
    };
    containerRef.current?.setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!dragging) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    const { maxX, maxY } = getMaxPan();
    setPosition({
      x: Math.max(-maxX, Math.min(maxX, dragRef.current.origX + dx)),
      y: Math.max(-maxY, Math.min(maxY, dragRef.current.origY + dy)),
    });
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (!dragging) return;
    setDragging(false);
    setAnimate(true);
    try {
      containerRef.current?.releasePointerCapture(e.pointerId);
    } catch {}
  };

  // Double-click: reset zoom if zoomed, otherwise zoom in
  const handleDoubleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    if (isZoomed) {
      resetZoom();
    } else {
      zoomAtPoint(e.clientX, e.clientY);
    }
  };

  const goPrev = () => {
    if (selectedIndex > 0) setSelectedIndex(selectedIndex - 1);
  };

  const goNext = () => {
    if (selectedIndex < images.length - 1) setSelectedIndex(selectedIndex + 1);
  };

  // Reset zoom when switching images
  useEffect(() => {
    setZoom(1);
    setPosition({ x: 0, y: 0 });
  }, [selectedIndex]);

  // Keyboard navigation (RTL: left key = next visually, right key = prev)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        setSelectedIndex((i) => Math.min(i + 1, images.length - 1));
      } else if (e.key === 'ArrowRight') {
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Escape' && isZoomed) {
        resetZoom();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [images.length, isZoomed]);

  if (!images || images.length === 0) {
    return (
      <div className="aspect-square bg-gradient-to-br from-pink-50 via-pink-50 to-pink-100/60 rounded-2xl flex items-center justify-center text-pink-300">
        بدون عکس
      </div>
    );
  }

  return (
    <div>
      {/* Main image */}
      <div
        ref={containerRef}
        className={`relative aspect-square bg-white rounded-2xl overflow-hidden border border-pink-100 shadow-[0_8px_24px_rgba(131,24,67,0.10)] select-none touch-none ${
          isZoomed
            ? dragging
              ? 'cursor-grabbing'
              : 'cursor-grab'
            : 'cursor-zoom-in'
        }`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onDoubleClick={handleDoubleClick}
      >
        {currentImage?.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={currentImage.image_url}
            alt={currentImage.alt_text || productName}
            className={`w-full h-full object-cover ${
              animate ? 'transition-transform duration-300' : ''
            }`}
            style={{
              transform: `translate(${position.x}px, ${position.y}px) scale(${zoom})`,
              transformOrigin: 'center',
            }}
            draggable={false}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-pink-300">
            بدون عکس
          </div>
        )}

        {/* Navigation arrows (only when multiple images AND not zoomed) */}
        {hasMultiple && !isZoomed && (
          <>
            {selectedIndex > 0 && (
              <button
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  goPrev();
                }}
                className="absolute top-1/2 -translate-y-1/2 right-3 w-10 h-10 rounded-full bg-white/95 backdrop-blur-sm shadow-md hover:bg-white hover:scale-110 transition-all flex items-center justify-center z-10"
                aria-label="عکس قبلی"
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#831843"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="m9 18 6-6-6-6" />
                </svg>
              </button>
            )}
            {selectedIndex < images.length - 1 && (
              <button
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  goNext();
                }}
                className="absolute top-1/2 -translate-y-1/2 left-3 w-10 h-10 rounded-full bg-white/95 backdrop-blur-sm shadow-md hover:bg-white hover:scale-110 transition-all flex items-center justify-center z-10"
                aria-label="عکس بعدی"
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#831843"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="m15 18-6-6 6-6" />
                </svg>
              </button>
            )}
          </>
        )}

        {/* Image counter badge */}
        {hasMultiple && !isZoomed && (
          <div className="absolute top-3 right-3 bg-white/95 backdrop-blur-sm text-pink-900 text-xs font-bold px-2.5 py-1 rounded-full shadow-md pointer-events-none">
            {selectedIndex + 1} / {images.length}
          </div>
        )}

        {/* Zoom hint / close */}
        {!isZoomed ? (
          <div className="absolute bottom-3 right-3 bg-white/95 backdrop-blur-sm text-pink-900 text-xs font-medium px-3 py-1.5 rounded-full shadow-md flex items-center gap-1.5 pointer-events-none">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.3-4.3M11 8v6M8 11h6" />
            </svg>
            <span>برای بزرگنمایی کلیک کنید</span>
          </div>
        ) : (
          <>
            <button
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                resetZoom();
              }}
              className="absolute top-3 left-3 bg-white/95 backdrop-blur-sm text-pink-900 text-xs font-bold px-3 py-1.5 rounded-full shadow-md hover:bg-white transition-colors z-10"
            >
              ✕ بستن
            </button>
            <div className="absolute bottom-3 right-3 bg-white/95 backdrop-blur-sm text-pink-900 text-xs font-medium px-3 py-1.5 rounded-full shadow-md pointer-events-none">
              برای جابجایی بکشید · دابل‌کلیک = بازگشت
            </div>
          </>
        )}
      </div>

      {/* Thumbnails */}
      {hasMultiple && (
        <div className="grid grid-cols-5 gap-2 mt-3">
          {images.map((img, idx) => (
            <button
              key={img.id}
              onClick={() => setSelectedIndex(idx)}
              className={`aspect-square rounded-lg overflow-hidden border-2 transition-all ${
                idx === selectedIndex
                  ? 'border-pink-800 shadow-md scale-105'
                  : 'border-gray-100 hover:border-pink-300 opacity-70 hover:opacity-100'
              }`}
            >
              {img.image_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={img.image_url}
                  alt={img.alt_text || `${productName} ${idx + 1}`}
                  className="w-full h-full object-cover"
                  draggable={false}
                />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}