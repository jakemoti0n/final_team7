import { toPixel } from '../../map'
import { dashedCircle, mapInfo, visitorStatus, type VisitorMap as MapData, type VisitorRobot } from './visitor'

/**
 * 방문자 지도: 행사장 지도 위에 LIMBO 위치만 큰 점으로. 방향·순찰 경로·목표 지점은 그리지 않는다.
 * 오래된 위치(stale)나 서버에서 받지 못하는 동안은 회색 점선 원으로 그려 "지금 여기 있다"로 읽히지 않게 한다.
 */
export function VisitorMap({ map, robots, stale, fit = true }: { map: MapData; robots: VisitorRobot[]; stale: boolean; fit?: boolean }) {
  const info = mapInfo(map)
  const unit = Math.max(map.width, map.height) / 100
  const shown = robots.filter(r => r.position)
  const label = shown.length ? `행사장 지도. ${shown.map(r => `${r.robot_id} ${old(r) ? '마지막 위치' : visitorStatus[r.status].label}`).join(', ')}` : '행사장 지도. 위치를 아는 로봇이 없습니다'
  function old(r: VisitorRobot) { return stale || r.position!.stale }
  // 지도 비율 그대로, 화면 높이의 70%를 넘지 않게 (넘치면 좁혀서 가운데)
  const width = `min(100%, calc(70vh * ${map.width / map.height}))`
  // 바탕은 자동 약도(있으면). 레이저 줄무늬가 없어 방문자가 읽기 쉽다
  const background = map.sketch ?? map.image
  return <div className="visitor-map"><svg viewBox={`0 0 ${map.width} ${map.height}`} style={fit ? { width } : undefined} role="img" aria-label={label}>
    {background ? <image href={background} width={map.width} height={map.height} className={map.sketch ? 'map-sketch' : 'map-image'} data-testid="visitor-map-background" /> : <rect width={map.width} height={map.height} className="map-blank" />}
    {/* 오래된 위치를 먼저 그려 지금 위치가 위에 오게 한다 */}
    {[...shown].sort((a, b) => Number(old(b)) - Number(old(a))).map(r => {
      const [x, y] = toPixel(info, r.position!.x, r.position!.y)
      return <g key={r.robot_id} data-testid="visitor-marker" data-robot={r.robot_id} className={`visitor-marker ${old(r) ? 'stale' : ''}`} transform={`translate(${x} ${y})`}>
        {!old(r) && <circle r={unit * 5.5} className="halo" />}
        <circle r={unit * 3} className="dot" strokeWidth={unit * .6} strokeDasharray={old(r) ? dashedCircle(unit * 3, 9) : undefined} />
        <text y={-unit * 4.6} fontSize={unit * 3.6} textAnchor="middle" strokeWidth={unit * .9}>{r.robot_id}</text>
      </g>
    })}
  </svg></div>
}
