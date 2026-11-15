import type { ReactNode } from 'react'

export function Card({ title, children, className = '' }: { title: string; children: ReactNode; className?: string }) {
  return <section className={`card ${className}`} aria-label={title}><h2 className="card-heading">{title}</h2>{children}</section>
}
