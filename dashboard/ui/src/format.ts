/** 화면에 보이는 시각·경과 시간 문구 */
export function ageText(age: number | null, delta = 0) {
  if (age === null) return '—'
  const value = Math.max(0, age + delta)
  return value < 1 ? `${value.toFixed(1)}초 전` : value < 60 ? `${Math.floor(value)}초 전` : `${Math.floor(value / 60)}분 ${Math.floor(value % 60)}초 전`
}
export function timeText(utc: string | null) {
  if (!utc) return '—'
  const date = new Date(utc)
  const dateFormat = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' })
  const time = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(date)
  return dateFormat.format(date) === dateFormat.format(new Date()) ? time : `${dateFormat.format(date)} ${time}`
}
