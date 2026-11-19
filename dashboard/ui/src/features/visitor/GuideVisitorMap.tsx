import { useState } from 'react'
import { GuideDrawing } from '../guide/GuideDrawing'
import { contentBox, inside, svgY, viewBoxAround, viewBoxOf } from '../guide/guide'
import { VisitorMap } from './VisitorMap'
import { asGuide, dashedCircle, visitorStatus, type VisitorGuide, type VisitorMap as MapData, type VisitorRobot } from './visitor'

/**
 * 방문자 화면의 메인 지도: 관제 화면에서 그린 안내 약도(구역·이름 또는 그림) 위에 LIMBO 위치.
 * 약도는 지도와 같은 m 좌표라 위치를 그대로 그린다. 왼쪽 아래 작은 창은 실제 지도(자동 약도) — 누르면 크게.
 */
export function GuideVisitorMap({ guide, map, robots, stale }: { guide: VisitorGuide; map: MapData | null; robots: VisitorRobot[]; stale: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const drawing = asGuide(guide)
  const content = contentBox(drawing)
  const box = content ? viewBoxAround(content, 1.5) : viewBoxOf(guide.bounds)
  const unit = Math.max(box[2], box[3]) / 100
  const view = { x_min: box[0], y_min: -(box[1] + box[3]), x_max: box[0] + box[2], y_max: -box[1] }
  const old = (r: VisitorRobot) => stale || r.position!.stale
  const shown = robots.filter(r => r.position)
  const inView = shown.filter(r => inside([r.position!.x, r.position!.y], view))
  const outside = shown.filter(r => !inView.includes(r))
  const label = `행사장 안내 약도${guide.areas.length ? ` (${guide.areas.map(a => a.name).join(', ')})` : ''}. ${inView.length ? inView.map(r => `${r.robot_id} ${old(r) ? '마지막 위치' : visitorStatus[r.status].label}`).join(', ') : '약도 안에 위치를 아는 로봇이 없습니다'}`
  const image = guide.image ? { href: guide.image.url, width: guide.image.width, height: guide.image.height, transform: guide.image.transform } : null
  const width = `min(100%, calc(70vh * ${box[2] / box[3]}))`
  return <div className="visitor-guide">
    <div className={`visitor-guide-frame ${expanded ? 'inset-open' : ''}`}>
      <svg viewBox={box.join(' ')} style={{ width }} role="img" aria-label={label} data-testid="visitor-guide-map">
        <rect x={box[0]} y={box[1]} width={box[2]} height={box[3]} className="guide-paper" />
        <GuideDrawing guide={drawing} image={image} showAreas={!guide.image || guide.image.show_areas} />
        {[...inView].sort((a, b) => Number(old(b)) - Number(old(a))).map(r => {
          const [x, y] = [r.position!.x, svgY(r.position!.y)]
          return <g key={r.robot_id} data-testid="visitor-marker" data-robot={r.robot_id} className={`visitor-marker ${old(r) ? 'stale' : ''}`} transform={`translate(${x} ${y})`}>
            {/* 약도에는 이름표가 있으므로 실제 지도 화면보다 조금 작게 */}
            {!old(r) && <circle r={unit * 4} className="halo" />}
            <circle r={unit * 2.3} className="dot" strokeWidth={unit * .5} strokeDasharray={old(r) ? dashedCircle(unit * 2.3, 8) : undefined} />
            <text y={-unit * 3.6} fontSize={unit * 3.2} textAnchor="middle" strokeWidth={unit * .8}>{r.robot_id}</text>
          </g>
        })}
      </svg>
      {map && <div className="visitor-inset" data-testid="visitor-inset">
        <button type="button" className="visitor-inset-toggle" aria-pressed={expanded} onClick={() => setExpanded(e => !e)}>{expanded ? '실제 지도 닫기' : '실제 지도'}</button>
        <VisitorMap map={map} robots={robots} stale={stale} fit={false} />
      </div>}
    </div>
    {outside.length > 0 && <p className="visitor-outside" role="status" data-testid="visitor-outside">{outside.map(r => r.robot_id).join(', ')}: 안내 약도 밖에 있습니다. {map ? '실제 지도에서 확인하세요.' : ''}</p>}
  </div>
}
