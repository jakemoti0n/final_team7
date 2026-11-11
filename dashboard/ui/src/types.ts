export const topicKeys = ['odom', 'lidar_raw', 'lidar_filtered', 'camera_raw'] as const
export type TopicKey = typeof topicKeys[number]
export const names: Record<TopicKey, string> = { odom: '주행 정보', lidar_raw: 'LiDAR 원본', lidar_filtered: 'LiDAR 필터 결과', camera_raw: '카메라 원본' }
export type Connection = 'checking' | 'connected' | 'delayed' | 'disconnected'
export type TopicStatus = 'never_received' | 'receiving' | 'delayed' | 'unknown'
export interface MotionValue { linear_speed_mps: number; angular_velocity_radps: number; last_received_at: string; age_ms: number; age_s?: number }
export type PatrolStateName = 'waiting_localization' | 'patrolling' | 'pausing' | 'paused' | 'completed' | 'failed'
export interface PatrolInfo { state: PatrolStateName | null; waypoint_index: number; waypoint_count: number; waypoint_name: string; has_resumable_task: boolean; reason: string; update_count: number; last_received_at: string | null; age_s: number | null }
export interface PoseInfo { frame_id: string | null; x: number | null; y: number | null; yaw: number | null; position_std_m: number | null; last_received_at: string | null; age_s: number | null; stale: boolean }
export type CommandName = 'pause' | 'resume' | 'start' | 'stop'
/** 텔레메트리 v3: Bridge가 로봇 컴퓨터에서 띄운 순찰 노드 (docs/CONTROL_API_DRAFT.md §1.3). v1·v2 Bridge면 null */
export interface Launcher { commands: CommandName[]; state: 'idle' | 'running' | 'exited'; pid: number | null; exit_code: number | null; waypoints_revision: string | null; log: string | null; other_patrol_running: boolean }
export type ServerStage = 'queued' | 'delivered' | 'accepted' | 'confirmed' | 'rejected' | 'service_unavailable' | 'no_response' | 'expired' | 'unconfirmed' | 'connection_lost'
export interface ServerCommand { request_id: string; command: CommandName; stage: ServerStage; message: string; issued_at: string; updated_at: string; age_s?: number }
export interface Alert { id: string; key: string; at: string; severity: 'info' | 'warning' | 'error'; message: string; kind: string; active: boolean }
/** 서버에 등록된 로봇 하나 (헤더의 로봇 선택 목록) */
/** 같은 지도를 쓰는 다른 로봇의 위치 (지도가 다르면 서버가 null로 보냄) */
export interface OtherPose { x: number; y: number; yaw: number; age_s: number | null; stale: boolean }
export interface RobotSummary { robot_id: string; status: Connection; last_received_at?: string | null; pose?: OtherPose | null }
export interface Snapshot {
  server_run_id: string; revision: number; server_utc: string; robot_id: string
  bridge: { status: Connection; last_received_at: string | null; age_s: number | null; session_id: string | null; sequence: number }
  topics: Record<TopicKey, { status: TopicStatus; last_received_at: string | null; age_s: number | null; received_count: number; receive_hz: number | null; last_receive_hz: number | null }>
  motion: { status: 'unconfirmed' | 'moving' | 'stopped' | 'unknown'; rotating: boolean; current: MotionValue | null; age_s: number | null; last_valid: MotionValue | null }
  alerts: Alert[]
  // 텔레메트리 v2 (docs/CONTROL_API_DRAFT.md §1, §3.4). v1 Bridge면 patrol·pose가 null
  patrol?: PatrolInfo | null; pose?: PoseInfo | null; command?: ServerCommand | null; map_available?: boolean
  // v3: 순찰 노드 실행 상태와, 서버가 판단한 "순찰 노드가 돌고 있음"(시작 거절·waypoint 편집 잠금 기준)
  launcher?: Launcher | null; patrol_running?: boolean
  // 여러 로봇: 서버가 아는 로봇 전체와 각 연결 상태 (이 snapshot은 robot_id 하나의 것)
  robots?: RobotSummary[]
  settings: { robot_id: string; bridge_delay_s: number; bridge_disconnect_s: number; browser_delay_s: number; topic_delay_s: Record<TopicKey, number>; linear_threshold_mps: number; angular_threshold_radps: number; alert_limit: number }
}
export interface View { snapshot: Snapshot | null; serverProblem: boolean; receivedMono: number }
export interface Provider { current: View; subscribe: (listener: (view: View) => void) => () => void; start: () => void; dispose: () => void }
