// 지도 좌표(m) → 그림 픽셀. 나중에 약도로 바꾸면 이 변환만 바꾼다 (docs/CONTROL_SCREEN.md B)
export interface Waypoint { name: string; type: string; x: number; y: number }
export interface MapInfo { resolution: number; origin: number[]; width: number; height: number; image: string | null; waypoints: Waypoint[] }

/** ROS 지도: 원점은 그림 왼쪽 아래, y는 위로. 그림은 y가 아래로 */
export function toPixel(map: MapInfo, x: number, y: number): [number, number] {
  return [(x - map.origin[0]) / map.resolution, map.height - (y - map.origin[1]) / map.resolution]
}
/** SVG rotate()는 시계 방향(도). ROS yaw는 반시계(라디안) */
export function headingDeg(yaw: number) { return -yaw * 180 / Math.PI }
/** 불확실성 원 반지름(픽셀): 표준편차의 2배(약 95%) */
export function uncertaintyPx(map: MapInfo, std: number | null) { return std == null ? 0 : 2 * std / map.resolution }

export function isMapInfo(value: unknown): value is MapInfo {
  const m = value as MapInfo
  return !!m && m.resolution > 0 && Array.isArray(m.origin) && m.origin.length >= 2 && m.width > 0 && m.height > 0 && Array.isArray(m.waypoints)
}
