import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../auth'
import { demoMap } from '../../demo'
import { isMapInfo, type MapInfo } from '../../map'
import { guideProblems, isGuideDocument, mapBounds, normalized, type Guide, type GuideDocument } from './guide'
import { demoGuide } from './demoGuide'

const HISTORY = 100

let demoSaved: GuideDocument | null = null
const demoImages = new Map<string, string>()   // 데모에서 올린 그림: 이름 → 이 탭의 blob 주소

export interface UploadedImage { file: string; width: number; height: number }

/** 약도 그림 주소 */
export function guideImageUrl(file: string, demo: boolean) { return demo ? demoImages.get(file) ?? '' : `/api/v1/guide/image/${encodeURIComponent(file)}` }

function imageSize(url: string) {
  return new Promise<[number, number]>((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve([img.naturalWidth, img.naturalHeight])
    img.onerror = () => reject(new Error('그림을 읽을 수 없습니다. PNG·JPG·WebP 파일인지 확인하세요.'))
    img.src = url
  })
}

const IMAGE_EXT: Record<string, string> = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp' }
export const MAX_IMAGE_MB = 10

/** 그림 올리기. 데모는 이 탭에만 둔다. 약도를 저장해야 쓰인다 */
export async function uploadGuideImage(file: File, demo: boolean): Promise<UploadedImage> {
  const ext = IMAGE_EXT[file.type]
  if (!ext) throw new Error('PNG·JPG·WebP 그림만 올릴 수 있습니다.')
  if (file.size > MAX_IMAGE_MB * 1024 * 1024) throw new Error(`그림은 ${MAX_IMAGE_MB} MB까지입니다.`)
  if (demo) {
    const url = URL.createObjectURL(file)
    const [width, height] = await imageSize(url)
    const name = `image-${[...crypto.getRandomValues(new Uint8Array(8))].map(b => b.toString(16).padStart(2, '0')).join('')}.${ext}`
    demoImages.set(name, url)
    return { file: name, width, height }
  }
  let response: Response
  try { response = await api('/api/v1/guide/image', { method: 'PUT', headers: { 'Content-Type': file.type }, body: file }) }
  catch { throw new Error('서버에 연결할 수 없습니다.') }
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new Error(body?.error?.code === 'image_too_large' ? `그림은 ${MAX_IMAGE_MB} MB까지입니다.` : body?.error?.message ? `그림을 올리지 못했습니다: ${body.error.message}` : '그림을 올리지 못했습니다.')
  return { file: body.file, width: body.width, height: body.height }
}
function demoDocument(): GuideDocument {
  demoSaved ??= { revision: 'demo', exists: true, file: 'human_test_map_guide.yaml', guide: demoGuide(), map: 'human_test_map.yaml', map_matches: true, map_bounds: mapBounds(demoMap) }
  return demoSaved
}

const same = (a: Guide, b: Guide) => JSON.stringify(normalized(a)) === JSON.stringify(normalized(b))

/** 약도 편집 데이터: 서버 약도와 기본 로봇 지도, 고치는 중인 사본(draft), 되돌리기, 저장 */
export function useGuide(demo: boolean) {
  const [doc, setDoc] = useState<GuideDocument | null>(null)
  const [map, setMap] = useState<MapInfo | null>(null)
  const [draft, setDraft] = useState<Guide | null>(null)
  // 되돌리기 기록은 ref에 두고 바뀔 때 다시 그린다 (state 갱신 함수 안에서 다른 state를 바꾸지 않게)
  const undoStack = useRef<Guide[]>([])
  const redoStack = useRef<Guide[]>([])
  const [, setHistoryVersion] = useState(0)
  const touched = () => setHistoryVersion(v => v + 1)
  const remember = (before: Guide) => { undoStack.current = [...undoStack.current.slice(-HISTORY + 1), before]; redoStack.current = []; touched() }
  const forget = () => { undoStack.current = []; redoStack.current = []; touched() }
  const [problem, setProblem] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)
  const [saving, setSaving] = useState(false)
  const draftRef = useRef<Guide | null>(null)
  draftRef.current = draft

  const load = useCallback(async (signal?: AbortSignal) => {
    if (demo) { const d = demoDocument(); setMap(demoMap); setDoc(d); setDraft(structuredClone(d.guide)); return }
    try {
      // 약도는 기본 로봇의 지도 좌표로 그린다 (로봇을 바꿔도 같은 지도)
      const [mapResponse, guideResponse] = await Promise.all([api('/api/v1/map', { signal }), api('/api/v1/guide', { signal })])
      const body = await guideResponse.json().catch(() => null)
      if (!guideResponse.ok) {
        const code = body?.error?.code
        setProblem(code === 'guide_not_configured' ? '서버에 약도 파일(guide_yaml)이나 지도(map_yaml)가 설정되지 않았습니다. 서버 설정을 확인하세요.'
          : code === 'guide_unavailable' ? `약도 파일을 읽을 수 없습니다. ${body?.error?.message ?? ''}` : '약도를 불러오지 못했습니다.')
        return
      }
      if (!isGuideDocument(body)) { setProblem('약도 응답 형식이 맞지 않습니다.'); return }
      const mapBody = mapResponse.ok ? await mapResponse.json().catch(() => null) : null
      setMap(isMapInfo(mapBody) ? mapBody : null)
      setDoc(body); setDraft(structuredClone(body.guide)); forget(); setProblem(null); setConflict(false)
    } catch { if (!signal?.aborted) setProblem('서버에 연결할 수 없습니다.') }
  }, [demo])
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort() }, [load])

  /** 되돌리기에 남기는 변경 */
  const apply = useCallback((next: Guide | ((g: Guide) => Guide)) => {
    const current = draftRef.current
    if (!current) return
    const value = typeof next === 'function' ? next(current) : next
    if (same(value, current)) return
    remember(current); draftRef.current = value; setDraft(value)
  }, [])
  /** 끄는 동안의 화면 갱신 (되돌리기에 남기지 않음). 끝나면 commit(시작 전 약도) */
  const preview = useCallback((value: Guide) => { draftRef.current = value; setDraft(value) }, [])
  const commit = useCallback((before: Guide) => {
    const current = draftRef.current
    if (!current || same(before, current)) return
    remember(before)
  }, [])
  const undo = useCallback(() => {
    const current = draftRef.current, previous = undoStack.current.at(-1)
    if (!current || !previous) return
    undoStack.current = undoStack.current.slice(0, -1); redoStack.current = [...redoStack.current, current]
    draftRef.current = previous; setDraft(previous); touched()
  }, [])
  const redo = useCallback(() => {
    const current = draftRef.current, next = redoStack.current.at(-1)
    if (!current || !next) return
    redoStack.current = redoStack.current.slice(0, -1); undoStack.current = [...undoStack.current, current]
    draftRef.current = next; setDraft(next); touched()
  }, [])

  const dirty = !!doc && !!draft && !same(draft, doc.guide)
  const problems = draft ? guideProblems(draft) : []

  const save = useCallback(async (): Promise<string> => {
    const current = draftRef.current
    if (!doc || !current) throw new Error('약도를 아직 불러오지 못했습니다.')
    const issues = guideProblems(current)
    if (issues.length) throw new Error(issues[0])
    const guide = normalized(current)
    if (demo) {
      demoSaved = { ...doc, guide }
      setDoc(demoSaved); setDraft(structuredClone(guide))
      return '데모 약도에 반영했습니다. 새로 고침하면 처음 상태로 돌아갑니다.'
    }
    setSaving(true)
    try {
      let response: Response
      try {
        response = await api('/api/v1/guide', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision: doc.revision, guide }) })
      } catch { throw new Error('서버에 연결할 수 없습니다.') }
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        if (body?.error?.code === 'revision_conflict') { setConflict(true); throw new Error('다른 화면에서 약도가 먼저 저장되었습니다. 서버 약도를 불러온 뒤 다시 고쳐 주세요.') }
        throw new Error(body?.error?.message ? `저장하지 못했습니다: ${body.error.message}` : '저장하지 못했습니다.')
      }
      if (!isGuideDocument(body)) throw new Error('저장 응답 형식이 맞지 않습니다.')
      setDoc(body); setDraft(structuredClone(body.guide))
      return `저장했습니다 (${body.file}). 방문자 화면에 바로 반영됩니다.`
    } finally { setSaving(false) }
  }, [demo, doc])

  const discard = useCallback(() => { if (doc) { setDraft(structuredClone(doc.guide)); forget() } }, [doc])

  return { doc, map, draft, problem, problems, conflict, saving, dirty, canUndo: undoStack.current.length > 0, canRedo: redoStack.current.length > 0,
    apply, preview, commit, undo, redo, save, discard, reload: () => load() }
}
export type GuideData = ReturnType<typeof useGuide>
