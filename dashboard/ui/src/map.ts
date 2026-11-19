// 지도 좌표(m) → 그림 픽셀. 나중에 약도로 바꾸면 이 변환만 바꾼다 (docs/CONTROL_SCREEN.md B)
export interface Waypoint { name: string; type: string; x: number; y: number }
/** image: 원본 SLAM 지도, sketch: 서버가 만든 자동 약도(원본과 영역·크기가 같음, 못 만들면 null) */
export interface MapInfo { resolution: number; origin: number[]; width: number; height: number; image: string | null; sketch?: string | null; waypoints: Waypoint[] }

/** ROS 지도: 원점은 그림 왼쪽 아래, y는 위로. 그림은 y가 아래로 */
export function toPixel(map: MapInfo, x: number, y: number): [number, number] {
  return [(x - map.origin[0]) / map.resolution, map.height - (y - map.origin[1]) / map.resolution]
}
/** 그림 픽셀 → ROS 지도 좌표(m). */
export function fromPixel(map: MapInfo, px: number, py: number): [number, number] {
  return [map.origin[0] + px * map.resolution, map.origin[1] + (map.height - py) * map.resolution]
}
/** SVG rotate()는 시계 방향(도). ROS yaw는 반시계(라디안) */
export function headingDeg(yaw: number) { return -yaw * 180 / Math.PI }
/** 불확실성 원 반지름(픽셀): 표준편차의 2배(약 95%) */
export function uncertaintyPx(map: MapInfo, std: number | null) { return std == null ? 0 : 2 * std / map.resolution }

export function isMapInfo(value: unknown): value is MapInfo {
  const m = value as MapInfo
  return !!m && m.resolution > 0 && Array.isArray(m.origin) && m.origin.length >= 2 && m.width > 0 && m.height > 0 && Array.isArray(m.waypoints)
}

/** 지도 바탕: 원본 SLAM 지도 또는 자동 약도. 브라우저에 기억한다 (기본은 약도) */
export type MapLayer = 'original' | 'sketch'
const LAYER_KEY = 'limbo.mapLayer'
export function readMapLayer(): MapLayer {
  try { return localStorage.getItem(LAYER_KEY) === 'original' ? 'original' : 'sketch' } catch { return 'sketch' }
}
export function saveMapLayer(layer: MapLayer) {
  try { localStorage.setItem(LAYER_KEY, layer) } catch { /* 저장 못 해도 화면은 동작 */ }
}
/** 실제로 그릴 바탕 그림. 약도가 없으면 원본 */
export function mapBackground(map: MapInfo, layer: MapLayer): { href: string | null; layer: MapLayer } {
  return layer === 'sketch' && map.sketch ? { href: map.sketch, layer: 'sketch' } : { href: map.image, layer: 'original' }
}
