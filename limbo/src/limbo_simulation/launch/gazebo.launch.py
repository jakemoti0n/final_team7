from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    TimerAction,
    AppendEnvironmentVariable,
    ExecuteProcess,
    OpaqueFunction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch.substitutions import (
    Command, LaunchConfiguration, PathJoinSubstitution, PythonExpression,
)
from ament_index_python.packages import (
    get_package_share_directory,
    get_package_prefix,
)
import os

def generate_launch_description():

    description_pkg = get_package_share_directory(
        "limbo_description"
    )

    simulation_pkg = get_package_share_directory(
        "limbo_simulation"
    )

    bookstore_models = os.path.join(
    simulation_pkg,
    "models"
    )

    bookstore_resource_path = AppendEnvironmentVariable(
        "GZ_SIM_RESOURCE_PATH",
        bookstore_models
    )

    # robot:=legacy면 이전 모델(0.45 m 정사각형, 높이 약 0.7 m), 아니면 v14 (기본)
    xacro_file = PathJoinSubstitution([
        description_pkg,
        "urdf",
        PythonExpression([
            "'legacy/limbo_legacy.urdf.xacro' if '", LaunchConfiguration("robot"),
            "' == 'legacy' else 'limbo.urdf.xacro'"
        ]),
    ])

    bridge_config = os.path.join(
        simulation_pkg,
        "config",
        "bridge.yaml"
    )

    # Gazebo가 package://limbo_description/... mesh를
    # 찾을 수 있도록 ROS install share 경로 등록
    gz_resource_path = os.path.join(
        get_package_prefix("limbo_description"),
        "share"
    )

    set_gz_resource_path = AppendEnvironmentVariable(
        "GZ_SIM_RESOURCE_PATH",
        gz_resource_path
    )

    # 카메라 높이·피치는 센서 배치 실험용 (limbo.urdf.xacro의 xacro:arg). 기본값은 URDF와 같다
    xacro_args = [
        " camera_z:=", LaunchConfiguration("camera_z"),
        " camera_pitch_deg:=", LaunchConfiguration("camera_pitch_deg"),
    ]
    robot_description = ParameterValue(
        Command(["xacro ", xacro_file] + xacro_args),
        value_type=str,
    )
    camera_z_arg = DeclareLaunchArgument("camera_z", default_value="0.50")
    camera_pitch_arg = DeclareLaunchArgument("camera_pitch_deg", default_value="0")

    world_arg = DeclareLaunchArgument(
        "world",
        default_value="human_test_world",
        description="limbo_simulation/worlds/<world>.sdf",
    )
    # 로봇이 쓰는 센서·물리는 서버가 만들고, GUI는 사람이 보는 3D 창일 뿐이다.
    # 끄면(-s) CPU를 많이 아낀다. 로봇·지도·사람 인식 결과는 RViz로 본다
    robot_arg = DeclareLaunchArgument(
        "robot",
        default_value="v14",
        description="v14(기본, 쓰레기통 로봇) 또는 legacy(이전 모델)",
    )
    gui_arg = DeclareLaunchArgument(
        "gui",
        default_value="true",
        description="false면 Gazebo 3D 창 없이 서버만 띄운다",
    )
    server_only_flag = PythonExpression(
        ["'' if '", LaunchConfiguration("gui"), "' == 'true' else '-s '"]
    )
    world_file = PathJoinSubstitution(
        [simulation_pkg, "worlds", [LaunchConfiguration("world"), ".sdf"]]
    )

    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("ros_gz_sim"),
                "launch",
                "gz_sim.launch.py",
            )
        ),
        # -r 없이 띄우면 일시정지 상태로 시작해 sim time과 TF가 멈추고 Nav2 bringup이 시간 초과된다
        launch_arguments={"gz_args": ["-r ", server_only_flag, world_file]}.items(),
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[
            {
                "robot_description": robot_description,
                "use_sim_time": True,
            }
        ],
        output="screen",
    )

    bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        parameters=[
            {
                "config_file": bridge_config,
                "use_sim_time": True,
            }
        ],
        output="screen",
    )

    spawn_robot = TimerAction(
        period=2.0,
        actions=[
            Node(
                package="ros_gz_sim",
                executable="create",
                arguments=[
                    "-topic", "robot_description",
                    "-name", "limbo",
                    "-allow_renaming", "true",
                    "-z", "0.02",
                ],
                output="screen",
            )
        ],
    )

    def start_movers(context):
        """worlds/<world>_movers.json이 있으면 그 물체들(예: rift 미니언)을 움직이는 스크립트를 띄운다"""
        world = LaunchConfiguration("world").perform(context)
        movers = os.path.join(simulation_pkg, "worlds", f"{world}_movers.json")
        if not os.path.exists(movers):
            return []
        return [ExecuteProcess(
            cmd=["python3", os.path.join(simulation_pkg, "scripts", "moving_obstacles.py"), movers],
            output="screen",
        )]

    return LaunchDescription([
        world_arg,
        robot_arg,
        gui_arg,
        camera_z_arg,
        camera_pitch_arg,
        set_gz_resource_path,
        bookstore_resource_path,
        gz_sim,
        robot_state_publisher,
        bridge,
        spawn_robot,
        OpaqueFunction(function=start_movers),
    ])  
