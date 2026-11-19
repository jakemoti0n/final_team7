import { useEffect, useState } from 'react'
import { Card } from '../components/Card'
import { setLeaveGuard } from '../navigation'
import { GuideCanvas, type Background, type Selection, type Tool } from '../features/guide/GuideCanvas'
import { GuidePanel, Swatch } from '../features/guide/GuidePanel'
import { guideImageUrl, useGuide, type UploadedImage } from '../features/guide/useGuide'
import { MainImage, placeImage } from '../features/guide/MainImage'
import { addPick, completePairs, ImageBoard, PairList, type Pick } from '../features/guide/Calibration'
import { fitTransform, type PointPair } from '../features/guide/guide'

export const leaveWarning = '저장하지 않은 약도 변경이 있습니다. 이 페이지를 떠나면 사라집니다. 떠날까요?'

const tools: { key: Tool; label: string; hint: string }[] = [
  { key: 'select', label: '선택', hint: '구역·표시점을 누르면 고르고, 끌면 옮깁니다. 빈 곳을 끌면 화면 이동, 휠로 확대·축소' },
  { key: 'rect', label: '사각형', hint: '끌어서 사각형 구역을 그립니다 (0.25 m 격자, Alt를 누르면 5 cm)' },
  { key: 'polygon', label: '다각형', hint: '꼭짓점을 차례로 누르고, 첫 점을 다시 누르거나 Enter·두 번 누르기로 닫습니다. Esc 취소, ⌫ 마지막 점 지우기' },
  { key: 'marker', label: '표시점', hint: '입구·안내데스크처럼 점으로 표시할 곳을 누릅니다' },
]

/** 약도 편집: 방문자 화면에 보일 구역과 이름을 지도 좌표(m) 위에 그린다. 기본 로봇의 지도 기준, 순찰 중에도 편집 가능 */
export function GuidePage({ demo }: { demo: boolean }) {
  const data = useGuide(demo)
  const { doc, map, draft, problem, problems, conflict, saving, dirty } = data
  const [tool, setTool] = useState<Tool>('select')
  const [category, setCategory] = useState('classroom')
  const [selection, setSelection] = useState<Selection>(null)
  const [background, setBackground] = useState<Background>('sketch')
  const [opacity, setOpacity] = useState(0.6)
  const [showWaypoints, setShowWaypoints] = useState(true)
  const [previewMode, setPreviewMode] = useState(false)
  const [message, setMessage] = useState('')
  const [imageOpacity, setImageOpacity] = useState(0.85)
  // 기준점으로 그림 맞추는 중: 올린 그림과 찍은 점 짝
  const [calib, setCalib] = useState<{ image: UploadedImage; pairs: Pick[] } | null>(null)
  const busy = dirty || !!calib

  // 저장하지 않고 떠나지 않게: 페이지 이동·로봇 바꾸기는 묻고, 탭 닫기·새로 고침은 브라우저가 묻는다
  useEffect(() => {
    setLeaveGuard(busy ? () => confirm(leaveWarning) : null)
    if (!busy) return () => setLeaveGuard(null)
    const onUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    addEventListener('beforeunload', onUnload)
    return () => { removeEventListener('beforeunload', onUnload); setLeaveGuard(null) }
  }, [busy])
  // 고른 항목이 되돌리기 등으로 사라지면 선택을 푼다
  useEffect(() => {
    if (!draft || !selection) return
    if ((selection.kind === 'area' ? draft.areas : draft.markers)[selection.index] === undefined) setSelection(null)
  }, [draft, selection])
  useEffect(() => {
    if (draft && !draft.categories.some(c => c.key === category)) setCategory(draft.categories[0]?.key ?? '')
  }, [draft, category])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing = (event.target as HTMLElement | null)?.closest?.('input, textarea, select')
      if (typing || !(event.ctrlKey || event.metaKey)) return
      const key = event.key.toLowerCase()
      if (key === 'z' && !event.shiftKey) { event.preventDefault(); data.undo() }
      else if (key === 'y' || (key === 'z' && event.shiftKey)) { event.preventDefault(); data.redo() }
      else if (key === 's') { event.preventDefault(); void save() }
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  })

  const save = async () => {
    if (!dirty || saving) return
    try { setMessage(await data.save()) } catch (err) { setMessage(err instanceof Error ? err.message : '저장하지 못했습니다.') }
  }

  if (problem) return <Card title="약도 편집"><p className="control-body" role="alert">{problem}</p></Card>
  if (!doc || !draft) return <Card title="약도 편집"><p className="control-body muted" role="status">약도를 불러오는 중입니다…</p></Card>
  const current = tools.find(t => t.key === tool)!
  const placed = draft.image ? { href: guideImageUrl(draft.image.file, demo), width: draft.image.width, height: draft.image.height, transform: draft.image.transform, opacity: previewMode ? 1 : imageOpacity } : null
  const mapHref = map ? map.sketch ?? map.image : null
  const startCalibration = (image: UploadedImage, pairs: PointPair[]) => { setPreviewMode(false); setSelection(null); setCalib({ image, pairs: pairs.map(p => ({ image: p.image, map: p.map })) }) }
  const calibFit = calib ? fitTransform(completePairs(calib.pairs)) : null
  const finishCalibration = () => {
    if (!calib || !calibFit) return
    const { guide, widened } = placeImage(draft, calib.image, completePairs(calib.pairs), calibFit.transform)
    data.apply(guide); setCalib(null)
    setMessage(`그림을 기준점 ${completePairs(calib.pairs).length}개로 맞췄습니다 (평균 어긋남 ${calibFit.rms.toFixed(2)} m).${widened ? ' 그림이 들어가도록 그리기 영역을 넓혔습니다.' : ''} 저장하면 방문자 화면에 쓰입니다.`)
  }
  if (calib) return <section className="card guide-calibrate" aria-label="기준점으로 그림 맞추기">
    <h2 className="card-heading">기준점으로 그림 맞추기</h2>
    <div className="control-body">
      <p>왼쪽 그림과 오른쪽 지도에서 <b>같은 곳</b>을 차례로 누르세요(번호가 짝입니다). 서로 멀리 떨어진 모서리·벽 끝 3곳 이상이 좋습니다.
        누르면 점, 끌면 이동, 휠로 확대. 3쌍이 되면 오른쪽 지도에 그림이 반투명하게 겹쳐 보입니다.</p>
      <div className="guide-calibrate-boards">
        <ImageBoard image={calib.image} href={guideImageUrl(calib.image.file, demo)} pairs={calib.pairs} onPick={p => setCalib({ ...calib, pairs: addPick(calib.pairs, 'image', p) })} />
        <GuideCanvas guide={draft} map={map} background={background === 'none' ? 'sketch' : background} opacity={opacity} showWaypoints={false} previewMode={false}
          tool="pick" category={category} selection={null} onSelect={() => {}} apply={data.apply} preview={data.preview} commit={data.commit} onMessage={setMessage}
          overlay={calibFit ? { href: guideImageUrl(calib.image.file, demo), width: calib.image.width, height: calib.image.height, transform: calibFit.transform, opacity: 0.5 } : null}
          picks={calib.pairs.flatMap((p, i) => p.map ? [{ point: p.map, label: String(i + 1), done: !!p.image }] : [])}
          onPick={p => setCalib({ ...calib, pairs: addPick(calib.pairs, 'map', p) })} />
      </div>
      <PairList pairs={calib.pairs} onRemove={i => setCalib({ ...calib, pairs: calib.pairs.filter((_, k) => k !== i) })} />
      <div className="guide-row">
        <button type="button" className="primary" disabled={!calibFit} onClick={finishCalibration}>이대로 맞추기</button>
        <button type="button" onClick={() => setCalib({ ...calib, pairs: [] })} disabled={!calib.pairs.length}>점 모두 지우기</button>
        <button type="button" onClick={() => { setCalib(null); setMessage('그림 맞추기를 취소했습니다.') }}>취소</button>
      </div>
    </div>
  </section>
  return <>
    <section className="card guide-savebar" aria-label="약도 저장">
      <div>
        <strong role="status" data-testid="guide-status">{dirty ? `저장하지 않은 변경이 있습니다` : doc.exists ? '저장된 약도와 같습니다' : '아직 저장한 약도가 없습니다'}</strong>
        <small className="muted">{demo ? '데모 약도입니다. 서버에 저장하지 않고 새로 고침하면 처음 상태로 돌아갑니다.' : `${doc.file} · 지도 ${doc.map} · 저장하면 방문자 화면에 바로 반영됩니다`}</small>
      </div>
      <div className="guide-row">
        <button type="button" onClick={data.undo} disabled={!data.canUndo} title="Ctrl+Z">되돌리기</button>
        <button type="button" onClick={data.redo} disabled={!data.canRedo} title="Ctrl+Y">다시 하기</button>
        <button type="button" onClick={() => { if (confirm('저장하지 않은 변경을 모두 버리고 저장된 약도로 돌아갈까요?')) { data.discard(); setSelection(null); setMessage('저장된 약도로 되돌렸습니다.') } }} disabled={!dirty}>변경 취소</button>
        {!demo && doc.exists && <a className="button-link" href="/api/v1/guide/file" download={doc.file}>내려받기</a>}
        <button type="button" className="primary" onClick={() => void save()} disabled={!dirty || saving || problems.length > 0} title="Ctrl+S">{saving ? '저장 중…' : '저장'}</button>
      </div>
    </section>
    {!doc.map_matches && <div className="guide-warning" role="alert">이 약도는 다른 지도({draft.map ?? '알 수 없음'})로 그렸습니다. 지금 지도({doc.map})와 좌표가 맞지 않을 수 있습니다.
      <button type="button" onClick={() => data.apply(g => ({ ...g, map: doc.map }))}>지금 지도 기준으로 표시</button></div>}
    {conflict && <div className="guide-warning" role="alert">다른 화면에서 약도가 먼저 저장되었습니다. 내 변경을 버리고 서버 약도를 불러와야 저장할 수 있습니다.
      <button type="button" onClick={() => { void data.reload(); setSelection(null); setMessage('서버 약도를 다시 불러왔습니다.') }}>서버 약도 불러오기</button></div>}
    {problems.length > 0 && <div className="guide-warning" role="alert">저장하기 전에 고칠 것: {problems[0]}{problems.length > 1 ? ` 외 ${problems.length - 1}건` : ''}</div>}
    <div className="guide-layout">
      <section className="card guide-board" aria-label="약도 그리기">
        <div className="guide-toolbar">
          <div className="guide-tools" role="radiogroup" aria-label="그리기 도구">{tools.map(t => <button key={t.key} type="button" role="radio" aria-checked={tool === t.key} disabled={previewMode} onClick={() => setTool(t.key)}>{t.label}</button>)}</div>
          <label className="guide-new-category">새 항목 종류<span className="guide-row"><Swatch category={draft.categories.find(c => c.key === category)} /><select value={category} onChange={e => setCategory(e.target.value)}>{draft.categories.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}</select></span></label>
          <label className="guide-check"><input type="checkbox" checked={previewMode} onChange={e => { setPreviewMode(e.target.checked); setTool('select') }} />방문자 미리보기</label>
        </div>
        <p className="guide-hint muted">{previewMode ? '방문자에게 보일 모습입니다. 지도 바탕·격자·순찰 지점은 빠집니다.' : current.hint}</p>
        <GuideCanvas guide={draft} map={map} background={background} opacity={opacity} showWaypoints={showWaypoints} previewMode={previewMode}
          tool={tool} category={category} selection={selection} onSelect={setSelection} apply={data.apply} preview={data.preview} commit={data.commit} onMessage={setMessage} image={placed} />
        <div className="guide-toolbar guide-view">
          <label>지도 바탕<select value={background} onChange={e => setBackground(e.target.value as Background)} disabled={previewMode}>
            <option value="sketch" disabled={!map?.sketch}>자동 약도</option><option value="original" disabled={!map?.image}>원본 지도</option><option value="none">없음</option></select></label>
          <label>바탕 진하기<input type="range" min="0.1" max="1" step="0.1" value={opacity} onChange={e => setOpacity(Number(e.target.value))} disabled={previewMode || background === 'none'} /></label>
          <label className="guide-check"><input type="checkbox" checked={showWaypoints} onChange={e => setShowWaypoints(e.target.checked)} disabled={previewMode} />순찰 지점 보기 (방문자에게는 안 보임)</label>
        </div>
        {message && <p className="guide-message" role="status" data-testid="guide-message">{message}</p>}
      </section>
      <section className="card guide-side" aria-label="약도 항목">
        <MainImage guide={draft} demo={demo} map={map} mapHref={mapHref} apply={data.apply} onCalibrate={startCalibration} onMessage={setMessage} imageOpacity={imageOpacity} setImageOpacity={setImageOpacity} />
        <GuidePanel guide={draft} map={map} selection={selection} onSelect={setSelection} apply={data.apply} /></section>
    </div>
  </>
}
