// gz-sim 시스템 플러그인: 토픽으로 받은 위치대로 actor(사람)를 옮긴다.
//
// 왜 필요한가: Gazebo actor는 SDF 시간표(trajectory)대로만 움직이고 set_pose 서비스는 actor를 옮기지 못한다
// (2026-10-14 확인). 사람이 로봇을 비켜 주는 소셜 포스는 파이썬(scripts/moving_obstacles.py)이 계산하고,
// 이 플러그인은 그 결과(gz.msgs.Pose_V, 이름 = actor 이름)를 받아 actor의 TrajectoryPose를 바꾼다.
// 걷는 애니메이션은 옮긴 거리만큼 시간을 진행시켜 발이 땅을 미끄러지지 않게 한다 (gz-sim FollowActor와 같은 방식).
//
// 월드 SDF에서:
//   <plugin filename="actor_pose_control" name="limbo::ActorPoseControl">
//     <topic>/limbo/actor_poses</topic>          <!-- 기본값 -->
//     <animation_x_vel>2.0</animation_x_vel>     <!-- 애니메이션 1초가 몇 m 걷는지. 숫자가 작으면 발이 빨리 움직임 -->
//   </plugin>
// actor는 <skin>·<animation>만 두고 trajectory 없이 <script><loop>true</loop><auto_start>true</auto_start></script>.

#include <chrono>
#include <mutex>
#include <string>
#include <unordered_map>

#include <gz/math/Pose3.hh>
#include <gz/msgs/pose_v.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/System.hh>
#include <gz/sim/components/Actor.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/components/Pose.hh>
#include <gz/transport/Node.hh>

namespace limbo
{

class ActorPoseControl
  : public gz::sim::System,
  public gz::sim::ISystemConfigure,
  public gz::sim::ISystemPreUpdate
{
public:
  void Configure(
    const gz::sim::Entity &,
    const std::shared_ptr<const sdf::Element> & sdf,
    gz::sim::EntityComponentManager &,
    gz::sim::EventManager &) override
  {
    topic_ = sdf->Get<std::string>("topic", "/limbo/actor_poses").first;
    anim_x_vel_ = sdf->Get<double>("animation_x_vel", 2.0).first;
    node_.Subscribe(topic_, &ActorPoseControl::OnPoses, this);
    gzmsg << "ActorPoseControl: listening on " << topic_ << std::endl;
  }

  void PreUpdate(const gz::sim::UpdateInfo & info, gz::sim::EntityComponentManager & ecm) override
  {
    if (info.paused) {
      return;
    }
    std::unordered_map<std::string, gz::math::Pose3d> commands;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      commands.swap(commands_);
    }
    if (commands.empty()) {
      return;
    }
    ecm.Each<gz::sim::components::Actor, gz::sim::components::Name>(
      [&](const gz::sim::Entity & entity, const gz::sim::components::Actor *,
      const gz::sim::components::Name * name) -> bool
      {
        auto it = commands.find(name->Data());
        if (it != commands.end()) {
          MoveActor(ecm, entity, it->second);
        }
        return true;
      });
  }

private:
  using TrajectoryPose = gz::sim::components::TrajectoryPose;
  using AnimationTime = gz::sim::components::AnimationTime;

  void OnPoses(const gz::msgs::Pose_V & msg)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto & p : msg.pose()) {
      commands_[p.name()] = gz::math::Pose3d(
        p.position().x(), p.position().y(), p.position().z(),
        p.orientation().w(), p.orientation().x(), p.orientation().y(), p.orientation().z());
    }
  }

  void MoveActor(
    gz::sim::EntityComponentManager & ecm, const gz::sim::Entity & entity,
    const gz::math::Pose3d & target)
  {
    auto * traj = ecm.Component<TrajectoryPose>(entity);
    auto * anim = ecm.Component<AnimationTime>(entity);
    if (!traj) {
      // 처음 명령: FollowActor와 같이 준비한다. actor의 SDF pose는 0으로 두고(TrajectoryPose가 월드 기준 위치가 됨),
      // 애니메이션 이름·시간 컴포넌트가 없으면 만든다
      gzmsg << "ActorPoseControl: taking control of actor [" << ecm.Component<gz::sim::components::Name>(entity)->Data() << "]" << std::endl;
      auto * pose = ecm.Component<gz::sim::components::Pose>(entity);
      if (pose) {
        *pose = gz::sim::components::Pose(gz::math::Pose3d::Zero);
        ecm.SetChanged(entity, gz::sim::components::Pose::typeId, gz::sim::ComponentState::OneTimeChange);
      }
      if (!ecm.Component<gz::sim::components::AnimationName>(entity)) {
        auto * actor = ecm.Component<gz::sim::components::Actor>(entity);
        if (actor && actor->Data().AnimationCount() > 0) {
          ecm.CreateComponent(entity, gz::sim::components::AnimationName(actor->Data().AnimationByIndex(0)->Name()));
        }
      }
      ecm.CreateComponent(entity, TrajectoryPose(target));
      if (!anim) {
        ecm.CreateComponent(entity, AnimationTime(std::chrono::steady_clock::duration::zero()));
      }
      return;
    }
    const double distance = (target.Pos() - traj->Data().Pos()).Length();
    *traj = TrajectoryPose(target);
    ecm.SetChanged(entity, TrajectoryPose::typeId, gz::sim::ComponentState::OneTimeChange);
    if (anim && anim_x_vel_ > 0.0) {
      const auto advance = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
        std::chrono::duration<double>(distance / anim_x_vel_));
      *anim = AnimationTime(anim->Data() + advance);
      ecm.SetChanged(entity, AnimationTime::typeId, gz::sim::ComponentState::OneTimeChange);
    }
  }

  std::string topic_;
  double anim_x_vel_{2.0};
  gz::transport::Node node_;
  std::mutex mutex_;
  std::unordered_map<std::string, gz::math::Pose3d> commands_;
};

}  // namespace limbo

GZ_ADD_PLUGIN(
  limbo::ActorPoseControl,
  gz::sim::System,
  limbo::ActorPoseControl::ISystemConfigure,
  limbo::ActorPoseControl::ISystemPreUpdate)
