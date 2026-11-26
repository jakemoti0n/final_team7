import { useEffect, useMemo, useRef, useState } from 'react'
import { visitorStatus, type EcoTree, type EcoView, type VisitorRobot } from '../features/visitor/visitor'
import { useDisplayData } from '../features/display/useDisplayData'
import { QrCode } from '../features/display/QrCode'
import { useDisplaySound } from '../features/display/useDisplaySound'
import {
  DEFAULT_TIMING, NO_PASSING, advance, demoEco, ecoText, localTime, locationText, locksRotation, passingStep, passingText, pickEvents, pickRobot,
  rotationPlan, titleSize, topic, type DisplayContent, type DisplaySlide, type Passing, type Rotation,
} from '../features/display/display'

const WIDTH = 1920, HEIGHT = 1080
// 장면 ⑤ 나무 그림. 원본은 signage/assets/images/tree_*.png (1024 px, 장마다 2 MB), 키오스크용으로 900 px WebP로 줄인 것
const TREES: Record<EcoTree, string> = {
  initial: new URL('../assets/display/tree-initial.webp', import.meta.url).href,
  positive: new URL('../assets/display/tree-positive.webp', import.meta.url).href,
  negative: new URL('../assets/display/tree-negative.webp', import.meta.url).href,
}

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
 * 장면 ① 로봇 위치 + 행사 안내 + 큰 QR, ② 팜플렛 + 작은 QR, ⑤ 분리수거 나무 + 작은 QR. 회전 규칙 R(①→②→①→⑤)은 display.ts의 advance.
 * ④ 「LIMBO가 지나갑니다」는 출발할 때 지금 장면 위에 띄우고 소리 한 번(passingStep). ③ 쓰레기 받음은 로봇 신호가 생긴 뒤.
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
  const timing = content?.timing ?? DEFAULT_TIMING
  const ecoOn = content?.eco?.enabled ?? true
  const plan = useMemo(() => rotationPlan(timing, slides.length, false, ecoOn), [timing, slides.length, ecoOn])

  // ④ 지나갑니다: 상태를 받거나 1초가 지날 때마다 판단. 새로 띄우면 소리 한 번
  const [passing, setPassing] = useState<Passing>(NO_PASSING)
  useEffect(() => { setPassing(p => passingStep(p, closed ? null : robot, problem, Date.now(), timing)) }, [now, robot, problem, closed, timing])
  const sound = useDisplaySound(content?.sound?.url ?? null)
  const played = useRef<number | null>(null)
  useEffect(() => {
    if (passing.lastAt === null || passing.until === null || played.current === passing.lastAt) return
    played.current = passing.lastAt
    sound.play()
  }, [passing.lastAt, passing.until, sound])
  const passingShown = passing.until !== null

  // 회전: 오버레이가 떠 있는 동안은 시계를 멈췄다가, 내려가면 멈춘 만큼 미뤄 원래 자리에서 이어 간다 (PRD v0.3 R)
  const [rotation, setRotation] = useState<Rotation>(() => ({ slot: 0, startedAt: Date.now(), round: 0 }))
  const locked = !closed && !problem && locksRotation(robot)
  const heldSince = useRef<number | null>(null)
  useEffect(() => {
    const t = now.getTime()
    if (passingShown) { heldSince.current ??= t; return }
    const held = heldSince.current === null ? 0 : t - heldSince.current
    heldSince.current = null
    setRotation(r => advance(held ? { ...r, startedAt: r.startedAt + held } : r, plan, t, locked))
  }, [now, plan, locked, passingShown])

  const scene = closed ? 'closed' : plan[rotation.slot]?.scene ?? 'location'
  const slide = slides.length ? slides[rotation.round % slides.length] : null
  const visitorUrl = `${location.origin}/visitor`
  // 서버와 끊기면 판정이 오래됐으므로 숫자 없이 초기 나무. 데모는 바퀴마다 세 상태를 차례로
  const eco: EcoView | null = demo ? demoEco(rotation.round) : problem ? null : state?.eco ?? null
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
          {scene === 'eco' && <EcoScene eco={eco} visitorUrl={visitorUrl} />}
        </div>
      </main>
      {passingShown && !closed && <PassingOverlay robot={robot} />}
      {sound.blocked && !closed && <div className="display-sound-hint" data-testid="display-sound-hint">화면을 한 번 누르면 안내 소리가 켜져요</div>}
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
    <MiniQr visitorUrl={visitorUrl} />
  </div>
}

/** 장면 ②⑤의 오른쪽 아래 작은 QR (300 px). 팜플렛은 이 모서리(약 400 × 460 px)를 비워 둔다 */
function MiniQr({ visitorUrl }: { visitorUrl: string }) {
  return <aside className="display-card display-mini-qr" aria-label="폰으로 지도 보기" data-testid="display-mini-qr">
    <QrCode value={visitorUrl} className="display-qr" label="방문자 안내 화면 주소 QR 코드" />
    <p>폰으로 지도 보기</p>
  </aside>
}

/** 장면 ⑤ 환경 피드백: 왼쪽 나무 그림, 오른쪽 문구, 오른쪽 아래 작은 QR. 그림 위에 글자를 얹지 않는다 */
function EcoScene({ eco, visitorUrl }: { eco: EcoView | null; visitorUrl: string }) {
  const text = ecoText(eco)
  return <div className="display-eco" data-testid="display-eco" data-tree={text.tree}>
    <img className="display-eco-tree" src={TREES[text.tree]} alt="" aria-hidden="true" />
    <section className="display-eco-text">
      <div className="display-eco-kicker">우리가 함께 키우는 나무</div>
      <h1 data-testid="display-eco-title">{text.title}</h1>
      {text.detail && <p className="display-eco-detail" data-testid="display-eco-detail">{text.detail}</p>}
      {text.hint && <p className="display-eco-hint" data-testid="display-eco-hint">{text.hint}</p>}
    </section>
    <MiniQr visitorUrl={visitorUrl} />
  </div>
}

function PassingOverlay({ robot }: { robot: VisitorRobot | null }) {
  const text = passingText(robot)
  return <div className="display-passing" role="status" data-testid="display-passing">
    <div className="display-passing-card">
      <svg className="display-passing-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 9v6h4l5 4V5L8 9H4z" /><path d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12" fill="none" />
      </svg>
      <h1>{text.title}</h1>
      <p data-testid="display-passing-detail">{text.detail}</p>
    </div>
  </div>
}
