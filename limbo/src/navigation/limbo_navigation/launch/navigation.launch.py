"""Nav2 실행 — 축별 yaml 을 조합해서 nav2_bringup/navigation_launch.py 에 넘긴다.

인자:
  planner        config/planner/<name>.yaml        (기본 navfn)
  controller     config/controller/<name>.yaml     (기본 mppi)
  use_perception true 면 costmap/with_human.yaml + controller/overlays/<controller>_human.yaml 추가
  robot          config/robot/<name>.yaml          (sim | real)
  use_sim_time / autostart  → nav2 launch 로 전달

예:
  ros2 launch limbo_navigation navigation.launch.py controller:=rpp planner:=smac_hybrid
  ros2 launch limbo_navigation navigation.launch.py use_perception:=true
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

from limbo_navigation.param_merge import resolve_files, write_merged


def _launch_setup(context, *args, **kwargs):
    config_dir = os.path.join(get_package_share_directory('limbo_navigation'), 'config')

    planner = LaunchConfiguration('planner').perform(context)
    controller = LaunchConfiguration('controller').perform(context)
    robot = LaunchConfiguration('robot').perform(context)
    use_perception = LaunchConfiguration('use_perception').perform(context).lower() in ('true', '1', 'yes')

    files = resolve_files(config_dir, planner, controller, use_perception, robot)
    merged_path = write_merged(files)

    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory('nav2_bringup'), 'launch', 'navigation_launch.py')
        ),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'autostart': LaunchConfiguration('autostart'),
            'params_file': merged_path,
        }.items(),
    )

    return [
        LogInfo(msg=f'[limbo_navigation] planner={planner} controller={controller} '
                    f'use_perception={use_perception} robot={robot}'),
        LogInfo(msg='[limbo_navigation] 파라미터 조합: ' + ', '.join(os.path.relpath(f, config_dir) for f in files)),
        LogInfo(msg=f'[limbo_navigation] 병합 파일: {merged_path}'),
        nav2_launch,
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('planner', default_value='navfn', description='config/planner/<name>.yaml'),
        DeclareLaunchArgument('controller', default_value='mppi', description='config/controller/<name>.yaml'),
        DeclareLaunchArgument('use_perception', default_value='true',
                              description='human_layer costmap + 컨트롤러 인지 오버레이 사용 여부'),
        DeclareLaunchArgument('robot', default_value='sim', description='config/robot/<name>.yaml (sim | real)'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('autostart', default_value='true'),
        OpaqueFunction(function=_launch_setup),
    ])
