import { bbox, labelFit, labelPoint, markerRadius, svgMatrix, svgY, type Category, type Guide, type Transform } from './guide'
import { MapIcon } from './icons'

export const GUIDE_INK = '#1F2A24'
const OUTLINE = '#2E3A33'

/**
 * 약도의 구역·표시점·이름표. SVG 좌표는 미터(x 그대로, y 뒤집음)라서 바깥 svg의 viewBox만 정하면 된다.
 * 편집 화면과 방문자 화면이 같이 쓴다. data-hit은 편집 화면이 누른 대상을 찾는 데 쓴다.
 */
export interface PlacedImage { href: string; width: number; height: number; transform: Transform; opacity?: number }

/** 그림 약도: 그림 픽셀 좌표를 변환 행렬로 지도 위에 놓는다 */
export function GuideImageLayer({ image }: { image: PlacedImage }) {
  return <image href={image.href} width={image.width} height={image.height} transform={svgMatrix(image.transform)} opacity={image.opacity ?? 1}
    preserveAspectRatio="none" data-testid="guide-image" pointerEvents="none" />
}

export function GuideDrawing({ guide, selected, labels = true, image, showAreas = true }: {
  guide: Guide; selected?: { kind: 'area' | 'marker'; index: number } | null; labels?: boolean
  image?: PlacedImage | null; showAreas?: boolean
}) {
  const byKey = new Map<string, Category>(guide.categories.map(c => [c.key, c]))
  const r = markerRadius(guide)
  const areas = showAreas ? guide.areas : []
  return <g className="guide-drawing">
    {image && <GuideImageLayer image={image} />}
    {areas.map((area, i) => {
      const category = byKey.get(area.category)
      const isSelected = selected?.kind === 'area' && selected.index === i
      return <polygon key={`a${i}`} data-hit={`area:${i}`} data-testid="guide-area" data-name={area.name}
        points={area.polygon.map(([x, y]) => `${x},${svgY(y)}`).join(' ')}
        fill={category?.color ?? '#FFFFFF'} stroke={isSelected ? 'var(--color-accent, #15803D)' : OUTLINE}
        strokeWidth={isSelected ? 3 : 1.4} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    })}
    {labels && areas.map((area, i) => {
      const category = byKey.get(area.category)
      const [x, y] = labelPoint(area.polygon)
      const { size, showText, showIcon } = labelFit(area.polygon, area.name)
      const icon = showIcon ? category?.icon ?? 'none' : 'none'
      const box = bbox(area.polygon)
      const iconSize = showText ? size * 1.25 : Math.min(1.2, Math.min(box.x_max - box.x_min, box.y_max - box.y_min) * 0.5)   // 글자 없이 아이콘만이면 구역에 맞춰
      const iconY = showText && icon !== 'none' ? svgY(y) - size * 0.75 : svgY(y)
      return <g key={`l${i}`} className="guide-label" pointerEvents="none" aria-hidden={!showText}>
        <MapIcon icon={icon} x={x} y={iconY} size={iconSize} color={GUIDE_INK} />
        {showText && <text x={x} y={icon !== 'none' ? svgY(y) + size * 1.05 : svgY(y) + size * 0.35} fontSize={size} textAnchor="middle" fill={GUIDE_INK}
          fontWeight={700} paintOrder="stroke" stroke="#FFFFFF" strokeWidth={size * 0.18} strokeLinejoin="round">{area.name}</text>}
      </g>
    })}
    {guide.markers.map((marker, i) => {
      const category = byKey.get(marker.category)
      const isSelected = selected?.kind === 'marker' && selected.index === i
      return <g key={`m${i}`} data-testid="guide-marker" data-name={marker.name}>
        <circle data-hit={`marker:${i}`} cx={marker.x} cy={svgY(marker.y)} r={r} fill={category?.color ?? '#FFFFFF'}
          stroke={isSelected ? 'var(--color-accent, #15803D)' : OUTLINE} strokeWidth={isSelected ? 3 : 1.4} vectorEffect="non-scaling-stroke" />
        <g pointerEvents="none"><MapIcon icon={category?.icon ?? 'none'} x={marker.x} y={svgY(marker.y)} size={r * 1.3} color={GUIDE_INK} /></g>
        {labels && <text x={marker.x + r * 1.4} y={svgY(marker.y) + r * 0.42} fontSize={r * 1.25} fill={GUIDE_INK} fontWeight={700} pointerEvents="none"
          paintOrder="stroke" stroke="#FFFFFF" strokeWidth={r * 0.25} strokeLinejoin="round">{marker.name}</text>}
      </g>
    })}
  </g>
}
