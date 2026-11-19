import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { fitTransform, type Point, type PointPair } from './guide'
import type { UploadedImage } from './useGuide'

export type Pick = { image?: Point; map?: Point }

/** 기준점 짝 목록에 그림 점·지도 점을 넣는다: 비어 있는 첫 짝에, 없으면 새 짝으로 */
export function addPick(pairs: Pick[], side: 'image' | 'map', point: Point): Pick[] {
  const index = pairs.findIndex(p => p[side] === undefined)
  if (index >= 0) return pairs.map((p, i) => i === index ? { ...p, [side]: point } : p)
  return [...pairs, { [side]: point }]
}
export const completePairs = (pairs: Pick[]): PointPair[] => pairs.filter(p => p.image && p.map).map(p => ({ image: p.image!, map: p.map! }))

/**
 * 그림 판: 그림 픽셀 좌표. 짧게 누르면 점 고르기, 끌면 이동, 휠로 확대. 찍은 점에 번호를 단다
 */
export function ImageBoard({ image, href, pairs, onPick }: { image: UploadedImage; href: string; pairs: Pick[]; onPick: (p: Point) => void }) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [box, setBox] = useState([0, 0, image.width, image.height])
  const drag = useRef<{ x: number; y: number; box: number[]; moved: boolean; point: Point } | null>(null)
  useEffect(() => { setBox([0, 0, image.width, image.height]) }, [image.file, image.width, image.height])
  const unit = Math.max(box[2], box[3]) / 100
  const toImage = (event: { clientX: number; clientY: number }): Point => {
    const m = svgRef.current!.getScreenCTM()
    if (!m) return [0, 0]
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(m.inverse())
    return [Math.round(Math.min(image.width, Math.max(0, p.x)) * 10) / 10, Math.round(Math.min(image.height, Math.max(0, p.y)) * 10) / 10]
  }
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const m = svg.getScreenCTM()
      if (!m) return
      const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(m.inverse())
      const f = event.deltaY > 0 ? 1.15 : 1 / 1.15
      setBox(([x, y, w, h]) => { const nw = Math.min(Math.max(w * f, 10), image.width * 3), nh = nw * h / w; return [p.x - (p.x - x) * nw / w, p.y - (p.y - y) * nh / h, nw, nh] })
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [image.width])
  const down = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return
    event.currentTarget.setPointerCapture(event.pointerId)
    drag.current = { x: event.clientX, y: event.clientY, box, moved: false, point: toImage(event) }
  }
  const move = (event: ReactPointerEvent<SVGSVGElement>) => {
    const d = drag.current
    if (!d) return
    if (Math.hypot(event.clientX - d.x, event.clientY - d.y) > 4) d.moved = true
    if (!d.moved) return
    const svg = svgRef.current!, s = Math.max(d.box[2] / svg.clientWidth, d.box[3] / svg.clientHeight)
    setBox([d.box[0] - (event.clientX - d.x) * s, d.box[1] - (event.clientY - d.y) * s, d.box[2], d.box[3]])
  }
  const up = () => { const d = drag.current; drag.current = null; if (d && !d.moved) onPick(d.point) }
  return <div className="guide-canvas guide-image-board">
    <svg ref={svgRef} viewBox={box.join(' ')} role="application" aria-label="약도 그림에서 기준점 고르기" data-testid="guide-image-board"
      onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={() => { drag.current = null }}>
      <image href={href} width={image.width} height={image.height} preserveAspectRatio="none" />
      {pairs.map((p, i) => p.image && <g key={i} className={`guide-pick ${p.map ? 'done' : ''}`} pointerEvents="none" data-testid="guide-pick-image">
        <circle cx={p.image[0]} cy={p.image[1]} r={unit * 1.1} vectorEffect="non-scaling-stroke" />
        <text x={p.image[0] + unit * 1.4} y={p.image[1] - unit * 1.2} fontSize={unit * 2.4}>{i + 1}</text></g>)}
    </svg>
    <div className="guide-zoom"><button type="button" onClick={() => setBox([0, 0, image.width, image.height])}>전체</button></div>
  </div>
}

/** 기준점 목록과 맞춘 결과 (점마다의 어긋남) */
export function PairList({ pairs, onRemove }: { pairs: Pick[]; onRemove: (index: number) => void }) {
  const done = completePairs(pairs)
  const fit = fitTransform(done)
  let k = 0
  const errors = pairs.map(p => p.image && p.map && fit ? fit.errors[k++] : null)
  return <div className="guide-pairs">
    {pairs.length ? <ol>{pairs.map((p, i) => <li key={i} data-testid="guide-pair">
      <span className="guide-pair-no">{i + 1}</span>
      <span>{p.image ? `그림 ${p.image[0].toFixed(0)}, ${p.image[1].toFixed(0)}` : '그림 점 고르기'}</span>
      <span>{p.map ? `지도 ${p.map[0].toFixed(2)}, ${p.map[1].toFixed(2)} m` : '지도 점 고르기'}</span>
      <span className={errors[i] != null && errors[i]! > 0.5 ? 'guide-error' : 'muted'}>{errors[i] != null ? `어긋남 ${errors[i]!.toFixed(2)} m` : ''}</span>
      <button type="button" className="icon-button" aria-label={`${i + 1}번 기준점 지우기`} onClick={() => onRemove(i)}>✕</button>
    </li>)}</ol> : <p className="muted">아직 기준점이 없습니다.</p>}
    <p role="status" data-testid="guide-fit">{done.length < 3 ? `짝이 맞는 기준점 ${done.length}개 · 3개 이상 필요합니다` : !fit ? '점들이 거의 한 줄에 있어 맞출 수 없습니다. 멀리 떨어진 모서리를 고르세요.'
      : `기준점 ${done.length}개 · 평균 어긋남 ${fit.rms.toFixed(2)} m${fit.rms > 0.5 ? ' · 크게 어긋난 점을 다시 찍어 보세요' : ''}`}</p>
  </div>
}
