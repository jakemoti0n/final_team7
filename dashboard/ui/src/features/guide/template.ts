import type { MapInfo } from '../../map'
import { templateSize, type Bounds } from './guide'

/**
 * 그림 약도용 틀(PNG): 그리기 영역 전체를 1 m = ppm px로. 지도 바탕, 1 m·5 m 격자, 좌표, 실제 지도 범위(점선).
 * 디자이너가 이 그림 위에 레이어를 올려 약도를 그리고 **같은 크기로** 내보내면 올릴 때 좌표가 저절로 맞는다.
 */
export async function makeTemplate(map: MapInfo | null, bounds: Bounds, ppm: number, mapHref: string | null): Promise<Blob> {
  const [width, height] = templateSize(bounds, ppm)
  const canvas = document.createElement('canvas')
  canvas.width = width; canvas.height = height
  const ctx = canvas.getContext('2d')!
  const px = (x: number) => (x - bounds.x_min) * ppm, py = (y: number) => (bounds.y_max - y) * ppm
  ctx.fillStyle = '#FFFFFF'; ctx.fillRect(0, 0, width, height)
  if (map && mapHref) {
    const img = new Image()
    img.src = mapHref
    try {
      await img.decode()
      ctx.globalAlpha = 0.6
      ctx.imageSmoothingEnabled = false
      ctx.drawImage(img, px(map.origin[0]), py(map.origin[1] + map.height * map.resolution), map.width * map.resolution * ppm, map.height * map.resolution * ppm)
      ctx.globalAlpha = 1
    } catch { /* 지도 그림을 못 읽어도 격자만으로 쓸 수 있다 */ }
  }
  for (let x = Math.ceil(bounds.x_min); x <= bounds.x_max; x++) {
    ctx.strokeStyle = x % 5 === 0 ? 'rgba(20,83,45,.45)' : 'rgba(0,0,0,.12)'; ctx.lineWidth = x % 5 === 0 ? 1.5 : 1
    ctx.beginPath(); ctx.moveTo(Math.round(px(x)) + .5, 0); ctx.lineTo(Math.round(px(x)) + .5, height); ctx.stroke()
  }
  for (let y = Math.ceil(bounds.y_min); y <= bounds.y_max; y++) {
    ctx.strokeStyle = y % 5 === 0 ? 'rgba(20,83,45,.45)' : 'rgba(0,0,0,.12)'; ctx.lineWidth = y % 5 === 0 ? 1.5 : 1
    ctx.beginPath(); ctx.moveTo(0, Math.round(py(y)) + .5); ctx.lineTo(width, Math.round(py(y)) + .5); ctx.stroke()
  }
  ctx.fillStyle = 'rgba(20,83,45,.8)'; ctx.font = `${Math.max(10, ppm * 0.45)}px sans-serif`
  for (let x = Math.ceil(bounds.x_min / 5) * 5; x <= bounds.x_max; x += 5) for (let y = Math.ceil(bounds.y_min / 5) * 5; y <= bounds.y_max; y += 5) ctx.fillText(`${x},${y}`, px(x) + 3, py(y) - 3)
  if (map) {
    ctx.setLineDash([8, 6]); ctx.strokeStyle = 'rgba(0,0,0,.55)'; ctx.lineWidth = 1.5
    ctx.strokeRect(px(map.origin[0]), py(map.origin[1] + map.height * map.resolution), map.width * map.resolution * ppm, map.height * map.resolution * ppm)
    ctx.setLineDash([])
  }
  ctx.fillStyle = '#14532D'; ctx.font = `bold ${Math.max(12, ppm * 0.6)}px sans-serif`
  ctx.fillText(`LIMBO 약도 틀 · 1 m = ${ppm} px · ${width}×${height} px · 크기를 바꾸지 말고 이 위에 그리세요`, 8, Math.max(16, ppm * 0.8))
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('틀을 만들지 못했습니다.')), 'image/png'))
}

export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = name
  document.body.append(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
