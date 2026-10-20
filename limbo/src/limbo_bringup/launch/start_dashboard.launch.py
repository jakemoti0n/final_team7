"""Start the Dashboard web server and ROS telemetry Bridge together."""

from pathlib import Path

from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, EmitEvent, ExecuteProcess,
                            OpaqueFunction, RegisterEventHandler)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration


def _repository_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / 'dashboard/config.json').is_file() and (parent / 'relay_prog').is_dir():
            return str(parent)
    raise RuntimeError('Cannot find dashboard/ and relay_prog/ beside the LIMBO workspace')


def _start_processes(context):
    root = Path(LaunchConfiguration('repo_root').perform(context)).expanduser().resolve()
    domain_id = LaunchConfiguration('ros_domain_id').perform(context)
    dashboard_dir = root / 'dashboard'
    dashboard_python = dashboard_dir / '.venv/bin/python'
    ui_index = dashboard_dir / 'ui/dist/index.html'
    ros_setup = Path('/opt/ros/jazzy/setup.bash')
    limbo_setup = root / 'limbo/install/setup.bash'
    relay_setup = root / 'relay_prog/install/setup.bash'
    bridge_executable = root / 'relay_prog/install/limbo_telemetry_bridge/lib/limbo_telemetry_bridge/bridge'
    bridge_config = root / 'relay_prog/src/limbo_telemetry_bridge/config/bridge.yaml'
    for path in (dashboard_python, ui_index, ros_setup, limbo_setup,
                 relay_setup, bridge_executable, bridge_config):
        if not path.is_file():
            raise RuntimeError(f'Required Dashboard/Bridge file is missing: {path}')

    environment = {'ROS_DOMAIN_ID': domain_id}
    dashboard = ExecuteProcess(
        cmd=[str(dashboard_python), '-m', 'uvicorn', 'server.app:app',
             '--host', '127.0.0.1', '--port', '8000', '--workers', '1'],
        cwd=str(dashboard_dir), additional_env=environment, output='screen',
        name='dashboard_server',
    )
    # Source all three ROS environments, then replace Bash with the actual Bridge.
    # Invoking ros2 run here would leave an untracked child when the wrapper exits.
    bridge = ExecuteProcess(
        cmd=['bash', '-c',
             'source "$1" && source "$2" && source "$3" && exec "$4" --config "$5"',
             'dashboard-bridge', str(ros_setup), str(limbo_setup),
             str(relay_setup), str(bridge_executable), str(bridge_config)],
        cwd=str(root), additional_env=environment, output='screen',
        name='telemetry_bridge',
    )
    return [
        dashboard,
        bridge,
        RegisterEventHandler(OnProcessExit(
            target_action=dashboard,
            on_exit=[EmitEvent(event=Shutdown(reason='Dashboard server exited'))],
        )),
        RegisterEventHandler(OnProcessExit(
            target_action=bridge,
            on_exit=[EmitEvent(event=Shutdown(reason='Telemetry Bridge exited'))],
        )),
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('repo_root', default_value=_repository_root(),
                              description='Directory containing dashboard/, limbo/, and relay_prog/'),
        DeclareLaunchArgument('ros_domain_id', default_value='97',
                              description='ROS domain shared with the running robot or simulation'),
        OpaqueFunction(function=_start_processes),
    ])
