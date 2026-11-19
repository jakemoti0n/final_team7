import { demoMap } from '../../demo'
import { emptyGuide, rectangle, type Guide } from './guide'

/** 데모 약도: 데모 지도(test_waypoints 배치) 위의 예시 구역. 서버를 부르지 않고 이 탭에서만 바뀐다 */
export function demoGuide(): Guide {
  const g = emptyGuide(demoMap, 'human_test_map.yaml')
  g.areas = [
    { name: '행사장', category: 'event', polygon: rectangle([-6.5, 3], [-1, 7]) },
    { name: '201 강의실', category: 'classroom', polygon: rectangle([1.5, 3], [7, 7]) },
    { name: '화장실', category: 'restroom', polygon: rectangle([4.5, -7], [7, -4]) },
    { name: '복도', category: 'corridor', polygon: [[-7, -1], [7, -1], [7, 1.5], [-7, 1.5]] },
  ]
  g.markers = [{ name: '정문', category: 'entrance', x: -6.5, y: -6.5 }, { name: '안내데스크', category: 'other', x: 0, y: -3 }]
  g.categories = g.categories.map(c => c.key === 'other' ? { ...c, icon: 'info' } : c)
  return g
}
