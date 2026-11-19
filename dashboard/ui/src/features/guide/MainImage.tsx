import { useState } from 'react'
import type { MapInfo } from '../../map'
import { boundsCovering, imageCorners, matchTemplate, templateSize, templateTransform, TEMPLATE_PX_PER_M, type Guide, type PointPair, type Transform } from './guide'
import { makeTemplate, saveBlob } from './template'
import { MAX_IMAGE_MB, uploadGuideImage, type UploadedImage } from './useGuide'

/**
 * 메인 약도 고르기: 구역 그리기 또는 그림 파일.
 * 그림은 (A) 틀을 내려받아 그 위에 그린 그림(크기 그대로)이면 바로 맞고, (B) 다른 그림은 기준점 3개 이상으로 맞춘다
 */
export function MainImage({ guide, demo, map, mapHref, apply, onCalibrate, onMessage, imageOpacity, setImageOpacity }: {
  guide: Guide; demo: boolean; map: MapInfo | null; mapHref: string | null
  apply: (next: Guide | ((g: Guide) => Guide)) => void
  onCalibrate: (image: UploadedImage, pairs: PointPair[]) => void
  onMessage: (m: string) => void
  imageOpacity: number; setImageOpacity: (v: number) => void
}) {
  const [imageMode, setImageMode] = useState(!!guide.image)
  const [busy, setBusy] = useState(false)
  const showImageTools = imageMode || !!guide.image
  const image = guide.image

  const download = async (ppm: number) => {
    setBusy(true)
    try { saveBlob(await makeTemplate(map, guide.bounds, ppm, mapHref), `limbo-guide-template-${ppm}pxm.png`); onMessage(`틀을 내려받았습니다 (1 m = ${ppm} px). 크기를 바꾸지 말고 그 위에 그린 뒤 「틀로 그린 그림 올리기」로 올리세요.`) }
    catch (err) { onMessage(err instanceof Error ? err.message : '틀을 만들지 못했습니다.') }
    finally { setBusy(false) }
  }
  const upload = async (file: File | undefined, how: 'template' | 'points') => {
    if (!file) return
    setBusy(true)
    try {
      const info = await uploadGuideImage(file, demo)
      if (how === 'points') { onCalibrate(info, []); return }
      const ppm = matchTemplate(guide.bounds, info.width, info.height)
      if (!ppm) {
        const sizes = TEMPLATE_PX_PER_M.map(p => templateSize(guide.bounds, p).join('×')).join(' 또는 ')
        onMessage(`그림 크기(${info.width}×${info.height})가 지금 그리기 영역의 틀(${sizes})과 다릅니다. 영역을 바꿨다면 틀을 다시 받거나 「기준점으로 맞추기」로 올리세요.`)
        return
      }
      apply(g => ({ ...g, image: { file: info.file, width: info.width, height: info.height, transform: templateTransform(g.bounds, ppm), points: [], show_areas: g.image?.show_areas ?? false } }))
      onMessage('틀로 그린 그림을 그리기 영역에 맞춰 놓았습니다. 저장하면 방문자 화면에 쓰입니다.')
    } catch (err) { onMessage(err instanceof Error ? err.message : '그림을 올리지 못했습니다.') }
    finally { setBusy(false) }
  }
  const uploaders = <div className="guide-uploads">
    <label className="button-link guide-file">틀로 그린 그림 올리기<input type="file" accept="image/png,image/jpeg,image/webp" aria-label="틀로 그린 그림 올리기" disabled={busy}
      onChange={e => { void upload(e.target.files?.[0], 'template'); e.target.value = '' }} /></label>
    <label className="button-link guide-file">다른 그림 올리고 기준점으로 맞추기<input type="file" accept="image/png,image/jpeg,image/webp" aria-label="기준점으로 맞출 그림 올리기" disabled={busy}
      onChange={e => { void upload(e.target.files?.[0], 'points'); e.target.value = '' }} /></label>
  </div>

  return <section aria-label="메인 약도" className="guide-section">
    <h3>메인 약도</h3>
    <div className="guide-mode" role="radiogroup" aria-label="메인 약도 방식">
      <label className="guide-check"><input type="radio" name="guide-main" checked={!showImageTools} onChange={() => {
        if (image && !confirm('그림을 빼고 구역 그리기를 메인 약도로 쓸까요? (구역은 그대로 남습니다)')) return
        setImageMode(false); if (image) apply(g => ({ ...g, image: null }))
      }} />구역 그리기</label>
      <label className="guide-check"><input type="radio" name="guide-main" checked={showImageTools} onChange={() => setImageMode(true)} />그림 파일</label>
    </div>
    {!showImageTools && <p className="muted">그린 구역과 이름이 방문자 화면의 약도가 됩니다.</p>}
    {showImageTools && <>
      {image ? <div className="guide-image-info" data-testid="guide-image-info">
        <strong>{image.width}×{image.height} px</strong>
        <small className="muted">{image.points.length ? `기준점 ${image.points.length}개로 맞춤` : '틀 크기로 맞춤'} · {image.file}</small>
        <label className="guide-check"><input type="checkbox" checked={image.show_areas} onChange={e => apply(g => g.image ? { ...g, image: { ...g.image, show_areas: e.target.checked } } : g)} />그림 위에 그린 구역도 보이기 (방문자 화면)</label>
        <label>그림 진하기 (편집 화면에서만)<input type="range" min="0.1" max="1" step="0.1" value={imageOpacity} onChange={e => setImageOpacity(Number(e.target.value))} /></label>
        <div className="guide-row">
          <button type="button" onClick={() => onCalibrate({ file: image.file, width: image.width, height: image.height }, image.points)}>기준점으로 다시 맞추기</button>
          <button type="button" className="danger" onClick={() => apply(g => ({ ...g, image: null }))}>그림 빼기</button>
        </div>
      </div> : <p className="muted">방문자 화면에 보일 약도 그림(PNG·JPG·WebP, {MAX_IMAGE_MB} MB까지)을 올립니다. 그림 위의 로봇 위치가 맞으려면 지도와 위치를 맞춰야 합니다.</p>}
      <ol className="guide-steps">
        <li><span>새로 그린다면: 틀을 받아 그 위에 그리고 <b>크기를 그대로</b> 내보내세요.</span>
          <span className="guide-row">{TEMPLATE_PX_PER_M.map(ppm => <button key={ppm} type="button" disabled={busy} onClick={() => void download(ppm)}>틀 내려받기 ({templateSize(guide.bounds, ppm).join('×')})</button>)}</span></li>
        <li><span>이미 있는 안내도라면: 올린 뒤 그림과 지도에서 같은 곳(모서리 등)을 3쌍 이상 찍어 맞추세요.</span></li>
      </ol>
      {uploaders}
      {busy && <small className="muted" role="status">처리 중…</small>}
    </>}
  </section>
}

/** 기준점 결과를 약도에 넣는다. 그림이 영역 밖으로 나가면 영역을 넓힌다 */
export function placeImage(g: Guide, image: UploadedImage, pairs: PointPair[], transform: Transform): { guide: Guide; widened: boolean } {
  const placed = { file: image.file, width: image.width, height: image.height, transform, points: pairs, show_areas: g.image?.show_areas ?? false }
  const bounds = boundsCovering(g.bounds, imageCorners(placed))
  const widened = JSON.stringify(bounds) !== JSON.stringify(g.bounds)
  return { guide: { ...g, bounds, image: placed }, widened }
}
