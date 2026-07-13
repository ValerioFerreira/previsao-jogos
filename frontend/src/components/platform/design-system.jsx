"use client";
import React from 'react';
import { cn } from '@/lib/utils';

export function Surface({ className, children, as: Tag = 'div', ...props }) {
  return (
    <Tag className={cn('surface p-6', className)} {...props}>
      {children}
    </Tag>
  );
}

export function SurfaceInset({ className, children, ...props }) {
  return (
    <div className={cn('surface-inset p-4', className)} {...props}>
      {children}
    </div>
  );
}

export function SectionHeader({ title, subtitle, icon: Icon, action, className }) {
  return (
    <div className={cn('section-header', className)}>
      <div className="section-header-row">
        <h2 className="section-title">
          {Icon && <Icon className="w-[18px] h-[18px] text-primary shrink-0" strokeWidth={1.75} />}
          {title}
        </h2>
        {action}
      </div>
      {subtitle && <p className="section-subtitle">{subtitle}</p>}
    </div>
  );
}

export function SectionDivider({ label }) {
  return (
    <div className="section-divider">
      <span className="section-divider-label">{label}</span>
    </div>
  );
}

export function DataMetric({ label, value, variant = 'default', className }) {
  const valueClass =
    variant === 'home' ? 'data-metric-value-home' :
    variant === 'away' ? 'data-metric-value-away' :
    'data-metric-value';

  return (
    <div className={cn('data-metric', className)}>
      <span className="data-metric-label">{label}</span>
      <span className={valueClass}>{value}</span>
    </div>
  );
}

export function Spinner({ size = 'default', className }) {
  return (
    <div className={cn('spinner', size === 'lg' && 'spinner-lg', className)} role="status" aria-label="Carregando">
      <span className="sr-only">Carregando...</span>
    </div>
  );
}

export function EmptyState({ children, className }) {
  return (
    <div className={cn('empty-state', className)}>
      <p className="empty-state-text">{children}</p>
    </div>
  );
}

export function SegmentControl({ options, value, onChange, className }) {
  return (
    <div className={cn('segment-control', className)} role="tablist">
      {options.map((opt) => (
        <button
          key={opt.value}
          role="tab"
          aria-selected={value === opt.value}
          onClick={() => onChange(opt.value)}
          className={cn('segment-item', value === opt.value && 'segment-item-active')}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
