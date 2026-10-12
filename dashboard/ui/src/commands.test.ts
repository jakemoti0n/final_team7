import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { CommandMachine, type Command, type Outcome } from './commands'
import { MockProvider } from './demo'
import { ageText, timeText } from './App'
beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())
describe('three independent stages and explicit outcomes', () => {
  for (const command of ['stop', 'resume', 'restart'] as Command[]) {
    for (const outcome of ['success', 'reject', 'no_response', 'no_confirmation'] as Outcome[]) {
      it(`${command} / ${outcome}`, () => {
        const finished = vi.fn()
        const machine = new CommandMachine(vi.fn(), finished)
        machine.start(command, outcome)
        expect(machine.current?.stages).toEqual(['running', 'waiting', 'waiting'])
        expect(machine.start(command, outcome)).toBeNull()
        vi.advanceTimersByTime(100)
        expect(machine.current?.stages).toEqual(['done', 'running', 'waiting'])
        vi.advanceTimersByTime(500)
        if (outcome === 'success' || outcome === 'no_confirmation') {
          expect(machine.current?.stages).toEqual(['done', 'done', 'running'])
          expect(machine.current?.result).toBe('pending')
        }
        vi.advanceTimersByTime(5000)
        expect(machine.current?.result).toBe(outcome === 'success' ? 'success' : outcome === 'reject' ? 'failed' : 'unknown')
        expect(finished).toHaveBeenCalledTimes(1)
        machine.dispose()
      })
    }
  }
})
it('late/foreign/out-of-order events cannot silently promote a terminal result', () => {
  const finished = vi.fn()
  const m = new CommandMachine(vi.fn(), finished)
  const id = m.start('stop', 'late')!
  m.event(id, 'confirmed')
  expect(m.current?.result).toBe('pending')
  vi.advanceTimersByTime(5100)
  expect(m.current?.result).toBe('unknown')
  vi.advanceTimersByTime(3000)
  m.event(id, 'confirmed')
  expect(m.current?.result).toBe('unknown')
  expect(finished).toHaveBeenCalledTimes(1)
  m.start('resume', 'no_response')
  m.event(id, 'response'); m.event(id, 'confirmed')
  expect(m.current?.stages).toEqual(['running', 'waiting', 'waiting'])
})
it('confirmation timeout exact boundary and late confirmation', () => {
  const m = new CommandMachine(vi.fn(), vi.fn())
  const id = m.start('restart', 'no_confirmation')!
  vi.advanceTimersByTime(5599)
  expect(m.current?.result).toBe('pending')
  vi.advanceTimersByTime(1)
  expect(m.current?.result).toBe('unknown')
  m.event(id, 'confirmed')
  expect(m.current?.result).toBe('unknown')
})
it('reset cancels every timer and result; disconnect is terminal at every stage', () => {
  for (const elapsed of [0, 100, 600]) {
    const finished = vi.fn(), m = new CommandMachine(vi.fn(), finished)
    m.start('restart', 'success'); vi.advanceTimersByTime(elapsed); m.disconnect()
    vi.advanceTimersByTime(10000)
    expect(m.current?.result).toBe('unknown'); expect(finished).toHaveBeenCalledTimes(1)
    m.start('stop', 'success'); m.reset(); vi.advanceTimersByTime(10000)
    expect(m.current).toBeNull(); expect(finished).toHaveBeenCalledTimes(1)
  }
})
it('mock isolation, patrol gating independent of speed, and reset', () => {
  const first = new MockProvider(), second = new MockProvider()
  first.start(); second.start()
  for (const patrol of ['patrolling', 'empty', 'unknown'] as const) {
    first.setPatrol(patrol); first.request('resume'); expect(first.machine.current).toBeNull()
  }
  first.setPatrol('paused'); first.request('stop'); vi.advanceTimersByTime(1600)
  expect(first.current.snapshot?.motion.current?.linear_speed_mps).toBe(.25)
  expect(first.machine.current?.result).toBe('success') // explicit event; speed did not change
  expect(first.current.snapshot?.alerts).toHaveLength(1)
  expect(second.current.snapshot?.alerts).toHaveLength(0)
  first.reset('normal'); vi.advanceTimersByTime(10000)
  expect(first.machine.current).toBeNull(); expect(first.current.snapshot?.alerts).toHaveLength(0)
  first.dispose(); second.dispose()
})
it('age and Seoul time formatting', () => {
  expect(ageText(null, 10)).toBe('—'); expect(ageText(-3)).toBe('0.0초 전')
  expect(ageText(.3)).toBe('0.3초 전'); expect(ageText(61.8)).toBe('1분 1초 전')
  expect(timeText('2000-01-01T00:00:00Z')).toBe('2000-01-01 09:00:00')
})
