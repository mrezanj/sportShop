'use client';

import { useEffect, useState } from 'react';
import type { Testimonial } from '@/lib/api';

interface Props {
  testimonials: Testimonial[];
}

const ROTATE_MS = 5000;
const TRANSITION_MS = 850;

export default function TestimonialsSlider({ testimonials }: Props) {
  const [current, setCurrent] = useState(0);
  const count = testimonials.length;

  useEffect(() => {
    if (count <= 1) return;
    const timer = setInterval(() => {
      setCurrent((c) => (c + 1) % count);
    }, ROTATE_MS);
    return () => clearInterval(timer);
  }, [count]);

  if (count === 0) return null;

  if (count === 1) {
    return (
      <div className="max-w-sm mx-auto">
        <TestimonialCard testimonial={testimonials[0]} highlighted />
      </div>
    );
  }

  if (count === 2) {
    return (
      <div className="grid md:grid-cols-2 gap-5 max-w-xl mx-auto">
        <TestimonialCard testimonial={testimonials[0]} highlighted />
        <TestimonialCard testimonial={testimonials[1]} />
      </div>
    );
  }

  return (
    <div className="relative max-w-2xl mx-auto h-[290px]">
      {testimonials.map((t, i) => {
        const diff = (i - current + count) % count;
        const isCurrent = diff === 0;
        const isNext = diff === 1;
        const isPrev = diff === count - 1;

        let style: React.CSSProperties;

        if (isCurrent) {
          style = {
            transform: 'translateX(0) scale(1)',
            opacity: 1,
            zIndex: 10,
            visibility: 'visible',
            transition: `all ${TRANSITION_MS}ms cubic-bezier(0.16, 1, 0.3, 1)`,
            willChange: 'transform, opacity',
          };
        } else if (isNext) {
          style = {
            transform: 'translateX(-48%) scale(0.80)',
            opacity: 0.40,
            zIndex: 5,
            visibility: 'visible',
            transition: `all ${TRANSITION_MS}ms cubic-bezier(0.16, 1, 0.3, 1)`,
            willChange: 'transform, opacity',
          };
        } else if (isPrev) {
          style = {
            transform: 'translateX(48%) scale(0.80)',
            opacity: 0.40,
            zIndex: 5,
            visibility: 'visible',
            transition: `all ${TRANSITION_MS}ms cubic-bezier(0.16, 1, 0.3, 1)`,
            willChange: 'transform, opacity',
          };
        } else {
          style = {
            transform: 'translateX(-200%) scale(0.5)',
            opacity: 0,
            zIndex: 1,
            visibility: 'hidden',
            transition: 'opacity 0s, transform 0s, visibility 0s',
          };
        }

        return (
          <div
            key={t.id}
            className="absolute inset-0 pointer-events-none"
            style={style}
          >
            <TestimonialCard testimonial={t} highlighted={isCurrent} />
          </div>
        );
      })}
    </div>
  );
}

function TestimonialCard({
  testimonial,
  highlighted = false,
}: {
  testimonial: Testimonial;
  highlighted?: boolean;
}) {
  return (
    <div

      className={`relative h-full flex flex-col rounded-2xl p-5 transition-all duration-300 overflow-hidden ${highlighted
        ? 'shadow-[0_10px_40px_-10px_rgba(190,24,93,0.45)]'
        : 'shadow-[0_8px_30px_-10px_rgba(190,24,93,0.30)]'
        }`}
      style={{
        background:
          'linear-gradient(to top, #f9a8d4 0%, #fbcfe8 55%, #fce7f3 100%)',
      }}

    >
      {/* Soft decorative glow */}
      <div className="absolute -top-10 -left-10 w-28 h-28 rounded-full bg-white/40 blur-2xl pointer-events-none" />
      <div className="absolute -bottom-10 -right-10 w-24 h-24 rounded-full bg-pink-300/40 blur-2xl pointer-events-none" />

      {/* Header: avatar + name + role + stars */}
      <div className="relative flex items-center gap-3 mb-3">
        <div className="w-11 h-11 rounded-full bg-gradient-to-br from-pink-500 to-pink-700 flex items-center justify-center text-white font-bold flex-shrink-0 overflow-hidden text-base shadow-md ring-2 ring-white/70">
          {testimonial.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={testimonial.avatar_url}
              alt={testimonial.name}
              className="w-full h-full object-cover"
            />
          ) : (
            testimonial.name.charAt(0)
          )}
        </div>

        <div className="min-w-0 flex-1">
          <p className="font-extrabold text-sm text-pink-950 truncate">
            {testimonial.name}
          </p>
          {testimonial.role && (
            <p className="text-[11px] font-medium text-pink-800/90 truncate">
              {testimonial.role}
            </p>
          )}
        </div>

        {/* Stars */}
        <div className="flex gap-0.5 flex-shrink-0">
          {Array.from({ length: 5 }).map((_, i) => (
            <span
              key={i}
              className={
                i < testimonial.rating
                  ? 'text-amber-500 text-sm leading-none'
                  : 'text-pink-300 text-sm leading-none'
              }
            >
              ★
            </span>
          ))}
        </div>
      </div>

      {/* Divider */}
      <div className="relative h-px bg-gradient-to-l from-transparent via-pink-400/40 to-transparent mb-3" />

      {/* Quote mark */}
      <div className="relative text-3xl text-pink-500/60 font-serif leading-none mb-1 select-none">
        ”
      </div>

      {/* Content */}
      <p className="relative text-gray-800 text-[13px] leading-relaxed flex-1">
        {testimonial.content}
      </p>
    </div>
  );
}