import type { IconName } from './guide'

/** 약도 아이콘 모양 (24×24, 선). 이름은 서버 guide.py ICONS와 같게 */
function shape(icon: IconName) {
  switch (icon) {
    case 'classroom': return <><rect x="3" y="4" width="18" height="12" rx="1" /><path d="M7 20h10M12 16v4M7 8h6M7 11h4" /></>
    case 'event': return <><path d="M4 21V4" /><path d="M4 4h13l-2 4 2 4H4" /></>
    case 'restroom': return <><circle cx="7" cy="5" r="2" /><path d="M5 10h4l1 5H8v5H6v-5H4z" /><circle cx="17" cy="5" r="2" /><path d="M15 10h4v5h-1v5h-2v-5h-1z" /></>
    case 'entrance': return <><path d="M14 4h5v16h-5" /><path d="M3 12h11M10 8l4 4-4 4" /></>
    case 'exit': return <><path d="M10 4H5v16h5" /><path d="M10 12h11M17 8l4 4-4 4" /></>
    case 'stairs': return <path d="M3 20h5v-5h5v-5h5V5h3" />
    case 'elevator': return <><rect x="5" y="3" width="14" height="18" rx="1" /><path d="M9 9l3-3 3 3M9 15l3 3 3-3" /></>
    case 'info': return <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7.5v.5" /></>
    case 'food': return <><path d="M6 3v8a2 2 0 0 0 4 0V3M8 11v10" /><path d="M17 21V3c-2 1-3 4-3 8h3" /></>
    case 'office': return <><rect x="3" y="7" width="18" height="13" rx="1" /><path d="M9 7V4h6v3M3 13h18" /></>
    case 'medical': return <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M12 8v8M8 12h8" /></>
    case 'restricted': return <><circle cx="12" cy="12" r="9" /><path d="M5.6 5.6l12.8 12.8" /></>
    case 'star': return <path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z" />
    default: return null
  }
}

/** 화면 글자 옆에 쓰는 아이콘 (CSS 크기) */
export function GuideIcon({ icon, className = 'guide-icon' }: { icon: IconName; className?: string }) {
  if (icon === 'none') return null
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{shape(icon)}</svg>
}

/** 약도 안(미터 좌표)에 그리는 아이콘: (x, y)를 가운데로 size 크기 */
export function MapIcon({ icon, x, y, size, color }: { icon: IconName; x: number; y: number; size: number; color: string }) {
  if (icon === 'none') return null
  return <svg x={x - size / 2} y={y - size / 2} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" overflow="visible">{shape(icon)}</svg>
}
