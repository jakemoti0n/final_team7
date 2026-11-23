import { useEffect, useMemo, useState } from 'react'
import { visitorStatus, type VisitorRobot } from '../features/visitor/visitor'
import { useDisplayData } from '../features/display/useDisplayData'
import { QrCode } from '../features/display/QrCode'
import {
  DEFAULT_TIMING, advance, localTime, locationText, locksRotation, pickEvents, pickRobot, rotationPlan, titleSize, topic,
  type DisplayContent, type DisplaySlide, type Rotation,
} from '../features/display/display'

const WIDTH = 1920, HEIGHT = 1080

/** 1920×1080 화면을 창 크기에 맞춰 비율을 지키며 줄이고 늘린다 (남는 곳은 검게) */
function useFit() {
  const measure = () => Math.min(window.innerWidth / WIDTH, window.innerHeight / HEIGHT)
  const [scale, setScale] = useState(measure)
  useEffect(() => {
    const update = () => setScale(measure())
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])
  return scale
}

/**
 * 로봇 하단 디스플레이 (/display): 로그인 없이 읽기만, 조작 없음. 근거 signage/docs/PRD_로봇_하단_디스플레이_v0.3.md
 * 장면 ① 로봇 위치 + 행사 안내 + 큰 QR, ② 팜플렛 + 작은 QR. 회전 규칙 R(①→②→①)은 display.ts의 advance.
 * ③ 쓰레기 받음·④ 지나갑니다는 다음 단계.
 */
export function DisplayPage({ demo, robotId }: { demo: boolean; robotId: string | null }) {
  const { state, problem, closed, content } = useDisplayData(demo)
  const scale = useFit()
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  const robot = pickRobot(state, robotId)
  const slides = content?.slides ?? []
  const plan = useMemo(() => rotationPlan(content?.timing ?? DEFAULT_TIMING, slides.length, false), [content?.timing, slides.length])
  const [rotation, setRotation] = useState<Rotation>(() => ({ slot: 0, startedAt: Date.now(), round: 0 }))
  const locked = !closed && !problem && locksRotation(robot)
  useEffect(() => { setRotation(r => advance(r, plan, now.getTime(), locked)) }, [now, plan, locked])

  const scene = closed ? 'closed' : plan[rotation.slot]?.scene ?? 'location'
  const slide = slides.length ? slides[rotation.round % slides.length] : null
  const visitorUrl = `${location.origin}/visitor`
  // 같은 장면끼리(①→①)는 다시 그리지 않아 깜빡이지 않게, 다른 장면·다른 팜플렛으로 바뀔 때만 0.6 s 페이드
  const sceneKey = scene === 'slides' && slide ? `slides-${slide.url}` : scene

  return <div className="display-stage">
    <div className="display-screen" style={{ transform: `translate(-50%, -50%) scale(${scale})` }} data-testid="display-screen" data-scene={scene}>
      <Hud robot={robot} problem={problem} closed={closed} now={now} />
      <main className="display-body">
        <div key={sceneKey} className={`display-scene display-scene-${scene}`}>
          {scene === 'closed' && <section className="display-card display-closed" data-testid="display-closed">
            <h1>지금은 안내를 하지 않습니다</h1><p>행사 기간에만 LIMBO 위치를 안내합니다.</p></section>}
          {scene === 'location' && <LocationScene robot={robot} problem={problem} content={content} now={now} visitorUrl={visitorUrl} />}
          {scene === 'slides' && slide && <SlideScene slide={slide} index={slides.indexOf(slide)} total={slides.length} visitorUrl={visitorUrl} />}
        </div>
      </main>
      {!closed && plan.length > 1 && <footer className="display-dots" aria-hidden="true" data-testid="display-dots">
        {plan.map((_, i) => <i key={i} className={i === rotation.slot ? 'on' : undefined} />)}</footer>}
      {demo && <div className="display-demo" data-testid="display-demo">DEMO · 가상 데이터</div>}
    </div>
  </div>
}

function Hud({ robot, problem, closed, now }: { robot: VisitorRobot | null; problem: boolean; closed: boolean; now: Date }) {
  // 서버와 끊기면 로봇 상태를 모르므로 「연결 끊김」, 그래도 시계는 계속 간다
  const status = closed ? null : problem ? { label: '연결 끊김', tone: 'bad' } : robot ? visitorStatus[robot.status] : null
  return <header className="display-hud" data-testid="display-hud">
    <div className="display-hud-brand"><span className="display-mark" aria-hidden="true">L</span><b>LIMBO 실시간 안내</b></div>
    <div className="display-hud-status">
      {status && <><i className={`display-dot tone-${status.tone}`} aria-hidden="true" />
        {/* 서버와 끊긴 것은 로봇이 끊긴 것과 다르므로 로봇 이름을 붙이지 않는다 */}
        <span data-testid="display-hud-status">{robot && !problem ? `${robot.robot_id} ` : ''}{status.label}</span><span aria-hidden="true">·</span></>}
      <time data-testid="display-clock">{localTime(now)}</time>
    </div>
  </header>
}

function LocationScene({ robot, problem, content, now, visitorUrl }: {
  robot: VisitorRobot | null; problem: boolean; content: DisplayContent | null; now: Date; visitorUrl: string
}) {
  const text = locationText(robot, problem)
  const progress = !problem && robot && (robot.status === 'patrolling' || robot.status === 'paused') ? robot.progress ?? null : null
  const events = pickEvents(content?.schedule ?? [], now)
  return <div className="display-location">
    <section className="display-card display-qr-card" aria-label="폰으로 지도 보기">
      <h2>폰으로 지도 보기</h2>
      <QrCode value={visitorUrl} className="display-qr" label="방문자 안내 화면 주소 QR 코드" />
      <p>카메라로 찍으면 지금 LIMBO 위치가 보여요</p>
    </section>
    <div className="display-right">
      <section className="display-card display-status" data-testid="display-status">
        <div className="display-kicker">{topic(robot?.robot_id ?? 'LIMBO')} 지금</div>
        <h1 style={{ fontSize: titleSize(text.title) }} data-testid="display-title">{text.title}</h1>
        {(text.badge || text.detail) && <div className="display-sub">
          {text.badge && <span className="display-pill" data-testid="display-badge">{text.badge}</span>}
          {text.detail && <span data-testid="display-detail">{text.detail}</span>}
        </div>}
        {progress && <div className="display-progress" data-testid="display-progress">
          <div className="display-track"><i style={{ width: `${Math.round(progress.done / progress.total * 100)}%` }} /></div>
          <span>{progress.done} / {progress.total} 지점</span>
        </div>}
      </section>
      <section className="display-card display-schedule" aria-label="행사 안내">
        <h3>행사 안내</h3>
        {events.length ? <ul data-testid="display-events">{events.map(({ event, state }) =>
          <li key={`${event.date}-${event.start}-${event.title}`} className={state} data-testid="display-event" data-state={state}>
            <b>{state === 'later' && event.date ? `${+event.date.slice(5, 7)}/${+event.date.slice(8)} ` : ''}{event.start}
              {state === 'now' && <small>지금</small>}</b>
            <span>{event.title}</span>
            {event.place && <em>{event.place}</em>}
          </li>)}</ul>
          : <p className="display-empty" data-testid="display-events-empty">예정된 행사가 없습니다.</p>}
        {content?.message && <p className="display-message" data-testid="display-message">{content.message}</p>}
      </section>
    </div>
  </div>
}

function SlideScene({ slide, index, total, visitorUrl }: { slide: DisplaySlide; index: number; total: number; visitorUrl: string }) {
  // 1920×1080 그림은 화면 전체(위 72 px는 HUD가 가린다). 비율이 다르면 흐린 같은 그림을 바탕에 깔고 가운데 맞춤
  return <div className="display-slide" data-testid="display-slide" data-file={slide.file}>
    <img className="display-slide-bg" src={slide.url} alt="" aria-hidden="true" />
    <img className="display-slide-fg" src={slide.url} alt={`행사장 팜플렛 ${index + 1}/${total}`} />
    <aside className="display-card display-mini-qr" aria-label="폰으로 지도 보기">
      <QrCode value={visitorUrl} className="display-qr" label="방문자 안내 화면 주소 QR 코드" />
      <p>폰으로 지도 보기</p>
    </aside>
  </div>
}
