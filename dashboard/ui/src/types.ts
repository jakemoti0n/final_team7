export const topicKeys = ['odom', 'lidar_raw', 'lidar_filtered', 'camera_raw'] as const
export type TopicKey = typeof topicKeys[number]
export const names: Record<TopicKey, string> = { odom: '주행 정보', lidar_raw: 'LiDAR 원본', lidar_filtered: 'LiDAR 필터 결과', camera_raw: '카메라 원본' }
export type Connection = 'checking' | 'connected' | 'delayed' | 'disconnected'
export type TopicStatus = 'never_received' | 'receiving' | 'delayed' | 'unknown'
export interface MotionValue { linear_speed_mps: number; angular_velocity_radps: number; last_received_at: string; age_ms: number; age_s?: number }
export type PatrolStateName = 'waiting_localization' | 'patrolling' | 'pausing' | 'paused' | 'completed' | 'failed'
export interface PatrolInfo { state: PatrolStateName | null; waypoint_index: number; waypoint_count: number; waypoint_name: string; has_resumable_task: boolean; reason: string; update_count: number; last_received_at: string | null; age_s: number | null }
export type FollowStateName = 'idle' | 'following' | 'holding' | 'stopped'
/** 텔레메트리 v2 선택 필드 follow (따라가기 상태, PROJECT.md 2-9 3단계). 내용은 전부 값이거나 전부 null */
export interface FollowInfo { state: FollowStateName | null; active: boolean | null; enrolled: boolean | null; visible: boolean | null; target_id: number | null; distance_m: number | null; reason: string | null; elapsed_s: number | null; lost_s: number | null; update_count: number; last_received_at: string | null; age_s: number | null }
export interface PoseInfo { frame_id: string | null; x: number | null; y: number | null; yaw: number | null; position_std_m: number | null; last_received_at: string | null; age_s: number | null; stale: boolean }
export type ServerStage = 'queued' | 'delivered' | 'accepted' | 'confirmed' | 'rejected' | 'service_unavailable' | 'no_response' | 'expired' | 'unconfirmed' | 'connection_lost'
export interface ServerCommand { request_id: string; command: 'pause' | 'resume' | 'follow_start' | 'follow_stop' | 'follow_enroll'; stage: ServerStage; message: string; issued_at: string; updated_at: string; age_s?: number }
export interface Alert { id: string; key: string; at: string; severity: 'info' | 'warning' | 'error'; message: string; kind: string; active: boolean }
export interface Snapshot {
  server_run_id: string; revision: number; server_utc: string; robot_id: string
  bridge: { status: Connection; last_received_at: string | null; age_s: number | null; session_id: string | null; sequence: number }
  topics: Record<TopicKey, { status: TopicStatus; last_received_at: string | null; age_s: number | null; received_count: number; receive_hz: number | null; last_receive_hz: number | null }>
  motion: { status: 'unconfirmed' | 'moving' | 'stopped' | 'unknown'; rotating: boolean; current: MotionValue | null; age_s: number | null; last_valid: MotionValue | null }
  alerts: Alert[]
  // 텔레메트리 v2 (docs/CONTROL_API_DRAFT.md §1, §3.4). v1 Bridge면 patrol·pose가 null
  patrol?: PatrolInfo | null; pose?: PoseInfo | null; command?: ServerCommand | null; map_available?: boolean
  follow?: FollowInfo | null   // 따라가기 상태. Bridge가 안 보내면 null
  settings: { robot_id: string; bridge_delay_s: number; bridge_disconnect_s: number; browser_delay_s: number; topic_delay_s: Record<TopicKey, number>; linear_threshold_mps: number; angular_threshold_radps: number; alert_limit: number }
}
export interface View { snapshot: Snapshot | null; serverProblem: boolean; receivedMono: number }
export interface Provider { current: View; subscribe: (listener: (view: View) => void) => () => void; start: () => void; dispose: () => void }
