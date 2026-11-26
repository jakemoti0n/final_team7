import { useRef, useState, type KeyboardEvent } from 'react'
import { GuideDrawing } from '../guide/GuideDrawing'
import { contentBox, inside, svgY, viewBoxAround, viewBoxOf } from '../guide/guide'
import { VisitorMap } from './VisitorMap'
import { asGuide, dashedCircle, visitorStatus, type VisitorGuide, type VisitorMap as MapData, type VisitorRobot } from './visitor'

/**
 * 방문자 화면의 메인 지도: 관제 화면에서 그린 안내 약도(구역·이름 또는 그림) 위에 LIMBO 위치.
 * 약도는 지도와 같은 m 좌표라 위치를 그대로 그린다. 실제 지도(LiDAR 자동 약도)가 있으면 위쪽 탭으로 둘을 바꿔 본다.
 * 두 판 모두 그려 두고 보이지 않는 쪽만 숨긴다(탭을 바꿀 때 그림을 다시 받지 않게).
 */
type Tab = 'guide' | 'lidar'
const tabs: { key: Tab; label: string }[] = [{ key: 'guide', label: '안내 지도' }, { key: 'lidar', label: 'LiDAR 지도' }]

export function GuideVisitorMap({ guide, map, robots, stale }: { guide: VisitorGuide; map: MapData | null; robots: VisitorRobot[]; stale: boolean }) {
  const [tab, setTab] = useState<Tab>('guide')
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({ guide: null, lidar: null })
  const current: Tab = map ? tab : 'guide'
  // WAI-ARIA 탭: 왼쪽·오른쪽 화살표, Home·End로 옮기며 바로 연다
  function onKey(e: KeyboardEvent) {
    const i = tabs.findIndex(t => t.key === current)
    const next = { ArrowLeft: i - 1, ArrowRight: i + 1, Home: 0, End: tabs.length - 1 }[e.key]
    if (next === undefined) return
    e.preventDefault()
    const key = tabs[(next + tabs.length) % tabs.length].key
    setTab(key)
    tabRefs.current[key]?.focus()
  }
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
    {map && <div className="visitor-tabs" role="tablist" aria-label="지도 종류" onKeyDown={onKey} data-testid="visitor-tabs">
      {tabs.map(t => <button key={t.key} type="button" role="tab" id={`visitor-tab-${t.key}`} aria-controls={`visitor-panel-${t.key}`}
        aria-selected={current === t.key} tabIndex={current === t.key ? 0 : -1} ref={el => { tabRefs.current[t.key] = el }}
        onClick={() => setTab(t.key)}>{t.label}</button>)}
    </div>}
    <div className="visitor-guide-frame" id="visitor-panel-guide" role={map ? 'tabpanel' : undefined} aria-labelledby={map ? 'visitor-tab-guide' : undefined} hidden={current !== 'guide'}>
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
    </div>
    {map && <div className="visitor-lidar" id="visitor-panel-lidar" role="tabpanel" aria-labelledby="visitor-tab-lidar" hidden={current !== 'lidar'} data-testid="visitor-lidar">
      <VisitorMap map={map} robots={robots} stale={stale} />
    </div>}
    {current === 'guide' && outside.length > 0 && <p className="visitor-outside" role="status" data-testid="visitor-outside">{outside.map(r => r.robot_id).join(', ')}: 안내 지도 밖에 있습니다. {map ? '「LiDAR 지도」 탭에서 확인하세요.' : ''}</p>}
  </div>
}
