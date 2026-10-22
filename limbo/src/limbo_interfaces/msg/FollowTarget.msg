# 따라가기 대상(운용자) 판정. person_detector가 카메라 프레임마다 /follow/target에 낸다 (PROJECT.md 2-9).
# 운용자는 미리 등록한 한 사람(직원). 형광 밴드가 주 근거, 하반신 색 서명과 위치 연속성이 보조 근거

std_msgs/Header header       # 위치의 기준 좌표계 (odom)

bool enrolled                # 운용자가 등록되어 있는지 (/follow/enroll)
bool found                   # 이번 프레임에 운용자를 찾았는지

# 찾았을 때: 사람 트랙 번호(PersonPrediction.person_id와 같은 번호), odom 위치·속도
int32 person_id
geometry_msgs/Point position
geometry_msgs/Vector3 velocity

# 판정 근거: band(밴드) | band_multi(밴드 찬 사람 여럿, 가까운 쪽) | track(밴드 안 보임, 같은 트랙 번호·서명 일치)
#            signature_mismatch(같은 번호인데 옷 색이 등록과 다름 → 안 믿음) | lost(못 찾음) | lost_timeout(lost_sec 넘게 못 찾아 대상 해제) | not_enrolled
string reason
int32 band_pixels            # 이번 프레임 밴드 색 픽셀 수
float32 similarity           # 등록 서명과의 유사도 (0~1)
float32 since_band_sec       # 마지막으로 밴드로 확인한 뒤 지난 시간
float32 lost_sec             # 못 찾은 채 지난 시간 (found=false일 때)
