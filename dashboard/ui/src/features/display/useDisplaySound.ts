import { useCallback, useEffect, useRef, useState } from 'react'
import { PASSING_SPEECH } from './display'

/** 아주 짧은 무음 WAV. 이걸 틀어 보아 브라우저가 소리를 막는지(자동 재생 정책) 미리 안다 */
function silentWav() {
  const samples = 800   // 8 kHz · 0.1 s, 8비트 모노 (무음 = 128)
  const bytes = new Uint8Array(44 + samples)
  const view = new DataView(bytes.buffer)
  const ascii = (at: number, s: string) => [...s].forEach((c, i) => { bytes[at + i] = c.charCodeAt(0) })
  ascii(0, 'RIFF'); view.setUint32(4, 36 + samples, true); ascii(8, 'WAVE'); ascii(12, 'fmt ')
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true)
  view.setUint32(24, 8000, true); view.setUint32(28, 8000, true); view.setUint16(32, 1, true); view.setUint16(34, 8, true)
  ascii(36, 'data'); view.setUint32(40, samples, true)
  bytes.fill(128, 44)
  return `data:audio/wav;base64,${btoa(String.fromCharCode(...bytes))}`
}

function koreanVoice() {
  if (typeof speechSynthesis === 'undefined') return null
  return speechSynthesis.getVoices().find(v => v.lang.toLowerCase().startsWith('ko')) ?? null
}

export interface DisplaySound {
  available: boolean   // 틀 소리가 있다 (파일 또는 한국어 음성)
  blocked: boolean     // 브라우저가 소리를 막고 있다: 화면을 한 번 눌러야 한다
  play: () => void     // 「지나갑니다」 한 번
}

/**
 * 장면 ④의 소리. 운영자가 넣은 파일(display.json의 sound)이 우선, 없으면 브라우저의 한국어 음성, 둘 다 없으면 소리 없이.
 * 브라우저는 사용자가 화면을 누르기 전에는 소리를 막는다(키오스크는 --autoplay-policy=no-user-gesture-required로 풀 수 있다).
 * 막혀 있으면 blocked를 알려 화면이 안내하고, 아무 곳이나 한 번 누르면 풀린다.
 */
export function useDisplaySound(url: string | null): DisplaySound {
  const audio = useRef<HTMLAudioElement | null>(null)
  const [voice, setVoice] = useState(koreanVoice)
  const [blocked, setBlocked] = useState(false)
  useEffect(() => {
    if (typeof speechSynthesis === 'undefined') return
    const update = () => setVoice(koreanVoice())
    speechSynthesis.addEventListener('voiceschanged', update)
    return () => speechSynthesis.removeEventListener('voiceschanged', update)
  }, [])
  useEffect(() => {
    audio.current = url ? Object.assign(new Audio(url), { preload: 'auto' }) : null
  }, [url])
  const available = url !== null || voice !== null

  // 켤 때 무음을 틀어 보아 막혀 있는지 안다. 누르면(또는 키를 누르면) 풀린다
  useEffect(() => {
    if (!available) { setBlocked(false); return }
    let stopped = false
    new Audio(silentWav()).play().then(() => { if (!stopped) setBlocked(false) })
      .catch((error: DOMException) => { if (!stopped && error.name === 'NotAllowedError') setBlocked(true) })
    const unlock = () => {
      setBlocked(false)
      void new Audio(silentWav()).play().catch(() => {})
    }
    window.addEventListener('pointerdown', unlock)
    window.addEventListener('keydown', unlock)
    return () => { stopped = true; window.removeEventListener('pointerdown', unlock); window.removeEventListener('keydown', unlock) }
  }, [available])

  const play = useCallback(() => {
    if (audio.current) {
      audio.current.currentTime = 0
      audio.current.play().catch((error: DOMException) => { if (error.name === 'NotAllowedError') setBlocked(true) })
    } else if (voice) {
      const say = new SpeechSynthesisUtterance(PASSING_SPEECH)
      say.voice = voice
      say.lang = voice.lang
      say.onerror = event => { if (event.error === 'not-allowed') setBlocked(true) }
      speechSynthesis.cancel()
      speechSynthesis.speak(say)
    }
  }, [voice])
  return { available, blocked, play }
}
