import { useMemo } from 'react'
import { qrModules, qrPath } from './qr'

/** QR 코드 (흰 여백 4칸 포함). 주소를 만들 수 없으면 아무것도 그리지 않는다 */
export function QrCode({ value, className, label }: { value: string; className?: string; label: string }) {
  const drawn = useMemo(() => {
    try {
      const modules = qrModules(value)
      return { size: modules.length + 8, path: qrPath(modules) }
    } catch {
      return null
    }
  }, [value])
  if (!drawn) return null
  return <svg className={className} viewBox={`0 0 ${drawn.size} ${drawn.size}`} shapeRendering="crispEdges" role="img" aria-label={label} data-testid="display-qr" data-value={value}>
    <rect width={drawn.size} height={drawn.size} fill="#fff" />
    <path d={drawn.path} fill="#111" />
  </svg>
}
