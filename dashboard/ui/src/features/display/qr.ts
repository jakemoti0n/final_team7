/**
 * QR 코드 만들기 (하단 디스플레이의 「폰으로 지도 보기」). 방문자 화면 주소 하나만 담으므로
 * 바이트 모드 · 오류 정정 M(약 15 %) · 버전 1–10(최대 213바이트)만 지원한다.
 * 알고리즘은 ISO/IEC 18004 그대로이며, 구성은 Project Nayuki의 QR 코드 생성기(MIT)를 따랐다.
 * 결과: modules[y][x] = true면 검은 칸. 둘레의 흰 여백(4칸)은 그리는 쪽에서 둔다.
 */

// 버전별 (오류 정정 M) 블록당 오류 정정 코드어 수, [블록 수, 블록당 데이터 코드어 수] 묶음
const BLOCKS: Record<number, { ec: number; groups: [number, number][] }> = {
  1: { ec: 10, groups: [[1, 16]] }, 2: { ec: 16, groups: [[1, 28]] }, 3: { ec: 26, groups: [[1, 44]] },
  4: { ec: 18, groups: [[2, 32]] }, 5: { ec: 24, groups: [[2, 43]] }, 6: { ec: 16, groups: [[4, 27]] },
  7: { ec: 18, groups: [[4, 31]] }, 8: { ec: 22, groups: [[2, 38], [2, 39]] }, 9: { ec: 22, groups: [[3, 36], [2, 37]] },
  10: { ec: 26, groups: [[4, 43], [1, 44]] },
}
const ALIGNMENT: Record<number, number[]> = {
  1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
}
export const QR_MAX_BYTES = 213

const dataCapacity = (version: number) => BLOCKS[version].groups.reduce((sum, [n, k]) => sum + n * k, 0)
const bit = (value: number, i: number) => ((value >>> i) & 1) !== 0

// ---- 리드-솔로몬 (GF(256), 원시 다항식 0x11D) ----
function multiply(x: number, y: number) {
  let z = 0
  for (let i = 7; i >= 0; i--) {
    z = (z << 1) ^ ((z >>> 7) * 0x11d)
    z ^= ((y >>> i) & 1) * x
  }
  return z
}
function divisor(degree: number) {
  const result = new Array<number>(degree - 1).fill(0).concat([1])
  let root = 1
  for (let i = 0; i < degree; i++) {
    for (let j = 0; j < result.length; j++) {
      result[j] = multiply(result[j], root)
      if (j + 1 < result.length) result[j] ^= result[j + 1]
    }
    root = multiply(root, 0x02)
  }
  return result
}
function remainder(data: number[], div: number[]) {
  const result = div.map(() => 0)
  for (const b of data) {
    const factor = b ^ (result.shift() as number)
    result.push(0)
    div.forEach((coef, i) => { result[i] ^= multiply(coef, factor) })
  }
  return result
}

/** 데이터 코드어 → 블록별 오류 정정을 붙여 섞은 최종 코드어 */
function codewords(version: number, data: number[]) {
  const { ec, groups } = BLOCKS[version]
  const div = divisor(ec)
  const blocks: number[][] = [], ecc: number[][] = []
  let at = 0
  for (const [count, size] of groups) for (let i = 0; i < count; i++) {
    const block = data.slice(at, at + size)
    at += size
    blocks.push(block)
    ecc.push(remainder(block, div))
  }
  const out: number[] = []
  const longest = Math.max(...blocks.map(b => b.length))
  for (let i = 0; i < longest; i++) for (const b of blocks) if (i < b.length) out.push(b[i])
  for (let i = 0; i < ec; i++) for (const e of ecc) out.push(e[i])
  return out
}

/** 바이트 모드 비트열 → 패딩까지 채운 데이터 코드어 */
function encodeData(version: number, bytes: Uint8Array) {
  const bits: number[] = []
  const push = (value: number, length: number) => { for (let i = length - 1; i >= 0; i--) bits.push((value >>> i) & 1) }
  push(0b0100, 4)                                  // 바이트 모드
  push(bytes.length, version <= 9 ? 8 : 16)        // 글자 수
  bytes.forEach(b => push(b, 8))
  const capacity = dataCapacity(version) * 8
  push(0, Math.min(4, capacity - bits.length))     // 종료 표시
  push(0, (8 - bits.length % 8) % 8)
  for (let pad = 0xec; bits.length < capacity; pad ^= 0xec ^ 0x11) push(pad, 8)
  const out: number[] = []
  for (let i = 0; i < bits.length; i += 8) out.push(bits.slice(i, i + 8).reduce((a, b) => (a << 1) | b, 0))
  return out
}

function penalty(m: boolean[][]) {
  const size = m.length
  let score = 0
  const line = (get: (i: number, j: number) => boolean) => {
    for (let i = 0; i < size; i++) {
      let run = 1
      for (let j = 1; j <= size; j++) {
        if (j < size && get(i, j) === get(i, j - 1)) run++
        else { if (run >= 5) score += run - 2; run = 1 }
      }
      // 찾기 패턴처럼 보이는 1:1:3:1:1 (앞뒤 흰 칸 4개)
      for (let j = 0; j + 11 <= size; j++) {
        const s = Array.from({ length: 11 }, (_, k) => get(i, j + k) ? 1 : 0).join('')
        if (s === '10111010000' || s === '00001011101') score += 40
      }
    }
  }
  line((i, j) => m[i][j])
  line((i, j) => m[j][i])
  for (let y = 0; y < size - 1; y++) for (let x = 0; x < size - 1; x++) {
    const c = m[y][x]
    if (c === m[y][x + 1] && c === m[y + 1][x] && c === m[y + 1][x + 1]) score += 3
  }
  const dark = m.reduce((sum, row) => sum + row.filter(Boolean).length, 0)
  score += Math.floor(Math.abs(dark * 20 - size * size * 10) / (size * size)) * 10
  return score
}

const MASKS: ((x: number, y: number) => boolean)[] = [
  (x, y) => (x + y) % 2 === 0, (_x, y) => y % 2 === 0, x => x % 3 === 0, (x, y) => (x + y) % 3 === 0,
  (x, y) => (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0, (x, y) => x * y % 2 + x * y % 3 === 0,
  (x, y) => (x * y % 2 + x * y % 3) % 2 === 0, (x, y) => ((x + y) % 2 + x * y % 3) % 2 === 0,
]

/** text를 담은 QR 칸 배열. 너무 길면(UTF-8 213바이트 초과) 오류 */
export function qrModules(text: string): boolean[][] {
  const bytes = new TextEncoder().encode(text)
  let version = 1
  const needed = (v: number) => Math.ceil((4 + (v <= 9 ? 8 : 16) + bytes.length * 8) / 8)
  while (version <= 10 && needed(version) > dataCapacity(version)) version++
  if (version > 10) throw new Error(`QR text is too long (${bytes.length} bytes, max ${QR_MAX_BYTES})`)
  const size = version * 4 + 17
  const modules = Array.from({ length: size }, () => new Array<boolean>(size).fill(false))
  const fixed = Array.from({ length: size }, () => new Array<boolean>(size).fill(false))
  const set = (x: number, y: number, dark: boolean) => { modules[y][x] = dark; fixed[y][x] = true }

  for (let i = 0; i < size; i++) { set(6, i, i % 2 === 0); set(i, 6, i % 2 === 0) }      // 타이밍
  for (const [cx, cy] of [[3, 3], [size - 4, 3], [3, size - 4]]) {                         // 찾기 패턴 + 흰 테두리
    for (let dy = -4; dy <= 4; dy++) for (let dx = -4; dx <= 4; dx++) {
      const x = cx + dx, y = cy + dy, d = Math.max(Math.abs(dx), Math.abs(dy))
      if (x >= 0 && x < size && y >= 0 && y < size) set(x, y, d !== 2 && d !== 4)
    }
  }
  const align = ALIGNMENT[version], last = align.length - 1
  align.forEach((ax, i) => align.forEach((ay, j) => {                                          // 정렬 패턴 (찾기 패턴 자리 셋은 빼고)
    if ((i === 0 && j === 0) || (i === 0 && j === last) || (i === last && j === 0)) return
    for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) set(ax + dx, ay + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1)
  }))
  const format = (mask: number) => {                                                           // 형식 정보 (M = 00)
    const value = mask
    let rem = value
    for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537)
    const bits = ((value << 10) | rem) ^ 0x5412
    for (let i = 0; i <= 5; i++) set(8, i, bit(bits, i))
    set(8, 7, bit(bits, 6)); set(8, 8, bit(bits, 7)); set(7, 8, bit(bits, 8))
    for (let i = 9; i < 15; i++) set(14 - i, 8, bit(bits, i))
    for (let i = 0; i < 8; i++) set(size - 1 - i, 8, bit(bits, i))
    for (let i = 8; i < 15; i++) set(8, size - 15 + i, bit(bits, i))
    set(8, size - 8, true)
  }
  format(0)
  if (version >= 7) {                                                                          // 버전 정보
    let rem = version
    for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25)
    const bits = (version << 12) | rem
    for (let i = 0; i < 18; i++) {
      const a = size - 11 + i % 3, b = Math.floor(i / 3)
      set(a, b, bit(bits, i)); set(b, a, bit(bits, i))
    }
  }

  const data = codewords(version, encodeData(version, bytes))                                 // 데이터 지그재그 배치
  let i = 0
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5
    for (let vert = 0; vert < size; vert++) for (let j = 0; j < 2; j++) {
      const x = right - j, upward = ((right + 1) & 2) === 0, y = upward ? size - 1 - vert : vert
      if (!fixed[y][x] && i < data.length * 8) { modules[y][x] = bit(data[i >>> 3], 7 - (i & 7)); i++ }
    }
  }

  // 8가지 마스크 중 벌점(긴 같은 색 줄·2×2 덩어리·찾기 패턴 닮은꼴·흑백 비율)이 가장 낮은 것
  let best: boolean[][] | null = null, bestScore = Infinity
  MASKS.forEach((mask, n) => {
    const masked = modules.map((row, y) => row.map((dark, x) => fixed[y][x] ? dark : dark !== mask(x, y)))
    const saved = modules.map(row => [...row])
    for (let y = 0; y < size; y++) modules[y] = masked[y]
    format(n)
    const score = penalty(modules)
    if (score < bestScore) { bestScore = score; best = modules.map(row => [...row]) }
    for (let y = 0; y < size; y++) modules[y] = saved[y]
  })
  return best!
}

/** SVG path (1칸 = 1단위, 여백 margin칸). 칸마다 사각형 대신 가로로 이어진 칸을 한 줄로 */
export function qrPath(modules: boolean[][], margin = 4) {
  const parts: string[] = []
  modules.forEach((row, y) => {
    for (let x = 0; x < row.length; x++) {
      if (!row[x]) continue
      let end = x
      while (end + 1 < row.length && row[end + 1]) end++
      parts.push(`M${x + margin} ${y + margin}h${end - x + 1}v1h${-(end - x + 1)}z`)
      x = end
    }
  })
  return parts.join('')
}
