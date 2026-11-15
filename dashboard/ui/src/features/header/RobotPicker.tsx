import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import type { RobotSummary } from '../../types'
import { Badge } from '../../components/Badge'

/** 헤더의 로봇 이름. 누르면 서버가 아는 로봇 목록이 열리고 고른 로봇의 상태로 화면을 바꾼다 */
export function RobotPicker({ current, robots, pending, disabled, onSelect }: { current: string; robots: RobotSummary[]; pending: boolean; disabled: boolean; onSelect: (robotId: string) => void }) {
  const [open, setOpen] = useState(false)
  const [focus, setFocus] = useState(0)
  const box = useRef<HTMLDivElement>(null)
  const list = robots.some(r => r.robot_id === current) ? robots : [{ robot_id: current, status: 'checking' as const }, ...robots]
  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => { if (!box.current?.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])
  const choose = (robotId: string) => { setOpen(false); if (robotId !== current) onSelect(robotId) }
  const toggle = () => { setFocus(Math.max(0, list.findIndex(r => r.robot_id === current))); setOpen(o => !o) }
  const keys = (event: KeyboardEvent) => {
    if (event.key === 'Escape') { setOpen(false); return }
    if (!open && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) { event.preventDefault(); toggle(); return }
    if (!open) return
    if (event.key === 'ArrowDown') { event.preventDefault(); setFocus(i => Math.min(list.length - 1, i + 1)) }
    else if (event.key === 'ArrowUp') { event.preventDefault(); setFocus(i => Math.max(0, i - 1)) }
    else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(list[focus].robot_id) }
  }
  return <div className="robot-picker" ref={box} onKeyDown={keys}>
    <button type="button" className="robot" aria-haspopup="listbox" aria-expanded={open} aria-label={`로봇 선택, 현재 ${current}`} disabled={disabled} title={disabled ? undefined : '다른 로봇 보기'} onClick={toggle}>{current}<span aria-hidden="true" className="caret">▾</span></button>
    {open && <div className="robot-menu"><ul role="listbox" aria-label="로봇 목록" aria-activedescendant={`robot-option-${focus}`} tabIndex={-1}>
      {list.map((r, i) => <li key={r.robot_id} id={`robot-option-${i}`} role="option" aria-selected={r.robot_id === current} className={`${i === focus ? 'focused' : ''} ${r.robot_id === current ? 'current' : ''}`} onMouseEnter={() => setFocus(i)} onClick={() => choose(r.robot_id)}>
        <strong>{r.robot_id}</strong><Badge status={r.status} /></li>)}
    </ul>{pending && <small className="robot-menu-note">진행 중인 요청은 {current}에서 계속 처리됩니다.</small>}{list.length === 1 && <small className="robot-menu-note">상태를 보낸 로봇이 하나뿐입니다. 다른 로봇은 Bridge가 연결되면 여기에 나타납니다.</small>}</div>}
  </div>
}
