import { useState } from 'react'
import { fromPixel, headingDeg, toPixel, uncertaintyPx, type MapInfo } from '../../map'
import type { View } from '../../types'
import { ageText } from '../../format'
import { Card } from '../../components/Card'

const FOLLOW_SPAN_M = 10   // 로봇 따라가기: 로봇 중심 가로세로 10 m
export function MapCard({ map, view, delta, onPick, onSelect }: { map: MapInfo | null; view: View; delta: number; onPick?: (point: [number, number]) => void; onSelect?: (robotId: string) => void }) {
  const [follow, setFollow] = useState(false)
  const pose = view.snapshot?.pose
  const patrol = view.serverProblem ? null : view.snapshot?.patrol
  const has = !!pose && pose.x != null && pose.y != null && pose.yaw != null
  const stale = view.serverProblem || !pose || pose.stale
  if (!map) return <Card title="지도" className="map-card"><p className="empty">{view.snapshot?.map_available === false ? '서버에 지도가 설정되지 않았습니다' : '지도를 불러오는 중입니다'}</p></Card>
  const points = map.waypoints.map(w => toPixel(map, w.x, w.y))
  const next = patrol?.state && patrol.state !== 'completed' ? patrol.waypoint_index : -1
  const [rx, ry] = has ? toPixel(map, pose!.x!, pose!.y!) : [0, 0]
  const span = FOLLOW_SPAN_M / map.resolution
  const box = follow && has ? [rx - span / 2, ry - span / 2, span, span] : [0, 0, map.width, map.height]
  const unit = Math.max(box[2], box[3]) / 100   // 표시 크기는 보이는 범위 기준 (확대해도 점·글자가 커지지 않게)
  // 같은 지도를 쓰는 다른 로봇. 서버 문제가 있으면 지금 위치라고 볼 수 없으므로 그리지 않는다
  const others = view.serverProblem ? [] : (view.snapshot?.robots ?? []).filter(r => r.robot_id !== view.snapshot?.robot_id && r.pose)
  // 지점 편집 중에는 지도 클릭이 위치 선택이므로 다른 로봇 표시를 누를 수 없게 한다
  const selectable = !!onSelect && !onPick
  return <Card title="지도" className="map-card">
    <div className={`map-frame ${onPick ? 'editing' : ''}`}><svg viewBox={box.join(' ')} role="img" aria-label="순찰 지도와 로봇 위치" onClick={event => {
      if (!onPick) return
      const svg = event.currentTarget, matrix = svg.getScreenCTM()
      if (!matrix) return
      const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
      if (point.x < 0 || point.x > map.width || point.y < 0 || point.y > map.height) return
      onPick(fromPixel(map, point.x, point.y))
    }}>
      {map.image ? <image href={map.image} width={map.width} height={map.height} className="map-image" /> : <rect width={map.width} height={map.height} className="map-blank" />}
      <polyline points={points.map(p => p.join(',')).join(' ')} className="route" strokeWidth={unit * .4} strokeDasharray={`${unit * 1.4} ${unit}`} />
      {map.waypoints.map((w, i) => { const [x, y] = points[i]; const tone = i === next ? 'next' : patrol && i < patrol.waypoint_index ? 'passed' : ''
        return <g key={w.name} className={`waypoint ${tone}`} data-testid="map-waypoint">{w.type === 'stop' ? <rect x={x - unit * 1.1} y={y - unit * 1.1} width={unit * 2.2} height={unit * 2.2} strokeWidth={unit * .35} /> : <circle cx={x} cy={y} r={unit * 1.1} strokeWidth={unit * .35} />}
          {i === next && <circle cx={x} cy={y} r={unit * 2.4} className="next-ring" strokeWidth={unit * .4} />}<text x={x + unit * 2} y={y - unit * 1.6} fontSize={unit * 3.4}>{w.name}</text></g> })}
      {others.map(r => { const [ox, oy] = toPixel(map, r.pose!.x, r.pose!.y)
        const go = selectable ? () => onSelect!(r.robot_id) : undefined
        return <g key={r.robot_id} data-testid="map-robot-other" className={`robot other ${r.pose!.stale ? 'stale' : ''} ${selectable ? 'selectable' : ''}`} transform={`translate(${ox} ${oy})`}
          role={selectable ? 'button' : undefined} tabIndex={selectable ? 0 : undefined} aria-label={`${r.robot_id}${r.pose!.stale ? ' (마지막 위치)' : ''}${selectable ? ' 로봇 보기' : ''}`}
          onClick={go ? event => { event.stopPropagation(); go() } : undefined} onKeyDown={go ? event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); go() } } : undefined}>
          {selectable && <title>{`${r.robot_id} 로봇 보기`}</title>}
          <circle r={unit * 4.6} className="hit" data-testid="map-robot-hit" strokeWidth={unit * .5} />
          <g transform={`rotate(${headingDeg(r.pose!.yaw)})`}><path d={`M ${unit * 3.8} 0 L ${-unit * 2.3} ${unit * 2.6} L ${-unit * 1.1} 0 L ${-unit * 2.3} ${-unit * 2.6} Z`} className="robot-mark" strokeWidth={unit * .3} /></g>
          <text x={unit * 3.4} y={unit * 4.6} fontSize={unit * 3}>{r.robot_id}</text></g> })}
      {has && <g data-testid="map-robot" className={`robot ${stale ? 'stale' : ''}`} transform={`translate(${rx} ${ry})`}>
        <circle r={Math.max(uncertaintyPx(map, pose!.position_std_m), unit * 2.6)} className="uncertainty" strokeWidth={unit * .25} />
        <g transform={`rotate(${headingDeg(pose!.yaw!)})`}><path d={`M ${unit * 4.4} 0 L ${-unit * 2.7} ${unit * 3} L ${-unit * 1.3} 0 L ${-unit * 2.7} ${-unit * 3} Z`} className="robot-mark" strokeWidth={unit * .3} /></g></g>}
    </svg></div>
    <div className="map-legend" data-testid="map-legend"><span role="status">{!has ? '로봇 위치 수신 대기' : stale ? `위치 확인 불가 · 마지막 위치 ${ageText(pose!.age_s, delta)}` : `위치 수신 ${ageText(pose!.age_s, delta)}${pose!.position_std_m != null ? ` · 오차 약 ±${(2 * pose!.position_std_m).toFixed(2)} m` : ''}`}</span>
      <button className="map-toggle" aria-pressed={follow} disabled={!has} onClick={() => setFollow(f => !f)}>{follow ? '전체 지도 보기' : '로봇 따라가기'}</button>
      {onPick && <span className="map-pick-hint">지도에서 지점 위치를 클릭하세요</span>}
      <span className="legend-keys">{others.length > 0 && <span><i className="key other" />다른 로봇{selectable ? ' (누르면 전환)' : ''}</span>}<span><i className="key next" />다음 목표</span><span><i className="key stop" />정지 지점</span><span><i className="key pass" />통과 지점</span></span></div>
  </Card>
}
