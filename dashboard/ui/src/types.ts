export const topicKeys = ['odom', 'lidar_raw', 'lidar_filtered', 'camera_raw'] as const
export type TopicKey = typeof topicKeys[number]
export const names: Record<TopicKey, string> = { odom: '주행 정보', lidar_raw: 'LiDAR 원본', lidar_filtered: 'LiDAR 필터 결과', camera_raw: '카메라 원본' }
export type Connection = 'checking' | 'connected' | 'delayed' | 'disconnected'
export type TopicStatus = 'never_received' | 'receiving' | 'delayed' | 'unknown'
export interface MotionValue { linear_speed_mps: number; angular_velocity_radps: number; last_received_at: string; age_ms: number; age_s?: number }
export interface Alert { id: string; key: string; at: string; severity: 'info' | 'warning' | 'error'; message: string; kind: string; active: boolean }
export interface Snapshot {
  server_run_id: string; revision: number; server_utc: string; robot_id: string
  bridge: { status: Connection; last_received_at: string | null; age_s: number | null; session_id: string | null; sequence: number }
  topics: Record<TopicKey, { status: TopicStatus; last_received_at: string | null; age_s: number | null; received_count: number; receive_hz: number | null; last_receive_hz: number | null }>
  motion: { status: 'unconfirmed' | 'moving' | 'stopped' | 'unknown'; rotating: boolean; current: MotionValue | null; age_s: number | null; last_valid: MotionValue | null }
  alerts: Alert[]
  settings: { robot_id: string; bridge_delay_s: number; bridge_disconnect_s: number; browser_delay_s: number; topic_delay_s: Record<TopicKey, number>; linear_threshold_mps: number; angular_threshold_radps: number; alert_limit: number }
}
export interface View { snapshot: Snapshot | null; serverProblem: boolean; receivedMono: number }
export interface Provider { current: View; subscribe: (listener: (view: View) => void) => () => void; start: () => void; dispose: () => void }
