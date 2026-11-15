import { useEffect, useReducer, useState } from 'react'
import { LiveProvider, robotQuery } from '../live'
import { MockProvider, demoMap } from '../demo'
import { LiveControl } from '../control'
import { isMapInfo, type MapInfo } from '../map'
import type { Provider, View } from '../types'
import { api } from '../auth'
import { waypointLockHint, type WaypointChange, type WaypointDocument } from '../features/waypoints/WaypointPanel'

/** 로봇 하나의 실시간 상태·명령·지도·waypoint. /demo면 가상 데이터(MockProvider), 아니면 서버(LiveProvider) */
export function useRobotData(robotId: string) {
  const [provider] = useState<Provider>(() => location.pathname === '/demo' ? new MockProvider() : new LiveProvider(robotId))
  const demo = provider instanceof MockProvider ? provider : null
  const [view, setView] = useState<View>(provider.current)
  const [now, setNow] = useState(performance.now())
  const [, redraw] = useReducer((n: number) => n + 1, 0)
  const [live] = useState(() => demo ? null : new LiveControl(redraw, undefined, robotId))
  const [liveMap, setLiveMap] = useState<MapInfo | null>(null)
  const [waypointDocument, setWaypointDocument] = useState<WaypointDocument | null>(null)
  const [waypointProblem, setWaypointProblem] = useState<string | null>(null)
  const map = demo ? { ...demoMap, waypoints: demo.waypoints } : liveMap
  useEffect(() => { const unsub = provider.subscribe(setView); provider.start(); const timer = setInterval(() => setNow(performance.now()), 200); return () => { clearInterval(timer); unsub(); provider.dispose() } }, [provider])
  const mapAvailable = !!view.snapshot?.map_available
  useEffect(() => {
    if (demo || liveMap || !mapAvailable) return
    const controller = new AbortController()
    api(`/api/v1/map${robotQuery(robotId)}`, { signal: controller.signal }).then(r => r.ok ? r.json() : null).then(value => { if (isMapInfo(value)) setLiveMap(value) }).catch(() => {})
    return () => controller.abort()
  }, [demo, liveMap, mapAvailable, robotId])
  useEffect(() => {
    if (demo || !liveMap) return
    const controller = new AbortController()
    api(`/api/v1/waypoints${robotQuery(robotId)}`, { signal: controller.signal }).then(r => { if (!r.ok) throw new Error(r.status === 404 ? 'Waypoint API를 사용할 수 없습니다. Dashboard 서버를 다시 시작하고 설정을 확인하세요.' : 'Waypoint 목록을 읽지 못했습니다.'); return r.json() }).then(value => {
      if (value && Array.isArray(value.waypoints) && typeof value.revision === 'string') {
        setWaypointDocument(value)
        setWaypointProblem(null)
        setLiveMap(current => current ? { ...current, waypoints: value.waypoints } : current)
      }
    }).catch(err => { if (!controller.signal.aborted) setWaypointProblem(err instanceof Error ? err.message : 'Waypoint 목록을 읽지 못했습니다.') })
    return () => controller.abort()
  }, [demo, !!liveMap, robotId])
  const changeWaypoint = async (change: WaypointChange) => {
    if (!waypointDocument) throw new Error('Waypoint 설정을 불러오지 못했습니다.')
    let response: Response
    try {
      response = await api(`/api/v1/waypoints${robotQuery(robotId)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision: waypointDocument.revision, ...change }) })
    } catch { throw new Error('서버에 연결할 수 없습니다.') }
    if (!response.ok) {
      if (response.status === 409) {
        const latest = await api(`/api/v1/waypoints${robotQuery(robotId)}`).then(r => r.ok ? r.json() : null).catch(() => null)
        if (latest) { setWaypointDocument(latest); setLiveMap(current => current ? { ...current, waypoints: latest.waypoints } : current) }
      }
      const body = await response.json().catch(() => null)
      throw new Error(body?.error?.code === 'patrol_active' ? waypointLockHint : body?.error?.code === 'revision_conflict' ? '다른 곳에서 경로가 변경되어 목록을 새로 불러왔습니다. 확인 후 다시 시도하세요.' : body?.error?.message || 'Waypoint 변경에 실패했습니다.')
    }
    const updated: WaypointDocument = await response.json()
    setWaypointDocument(updated)
    setLiveMap(current => current ? { ...current, waypoints: updated.waypoints } : current)
  }
  return { provider, demo, view, now, live, map, waypointDocument, waypointProblem, changeWaypoint }
}
