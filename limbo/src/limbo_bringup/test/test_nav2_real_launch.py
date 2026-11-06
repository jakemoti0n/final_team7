"""No-device checks for command isolation and real AMCL initialization."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
import yaml
from launch import LaunchContext

ROOT = Path(__file__).resolve().parents[4]
LAUNCH = ROOT / 'limbo/src/limbo_bringup/launch/start_nav2_real.launch.py'


def nodes(topic):
    spec = importlib.util.spec_from_file_location('real_nav_test', LAUNCH)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    context = LaunchContext()
    context.launch_configurations.update(cmd_vel_out=topic,
        params_file=str(ROOT / 'limbo/src/limbo_navigation/config/nav2_real.yaml'))
    with patch.object(module, 'Node', Mock()) as node:
        module._nodes(context)
    calls={call.kwargs['name']: call.kwargs for call in node.call_args_list}
    for name,call in calls.items():
        if name=='lifecycle_manager_navigation':continue
        param=call['parameters'][0];filename=Path(param.evaluate(context))
        call['effective_params']=yaml.safe_load(filename.read_text())[name]['ros__parameters']
        param.cleanup()
    return calls


def test_preview_chain_cannot_publish_real_cmd_vel():
    calls = nodes('/limbo/nav2_preview/cmd_vel')
    assert len(calls) == 9
    assert not any('roboclaw' in c['package'] or c['package']=='limbo_hardware' for c in calls.values())
    for name in ['controller_server','behavior_server','velocity_smoother']:
        assert dict(calls[name]['remappings'])['cmd_vel']=='/limbo/nav2_preview/cmd_vel_nav'
    assert dict(calls['velocity_smoother']['remappings'])['cmd_vel_smoothed']=='/limbo/nav2_preview/cmd_vel_smoothed'
    p=calls['collision_monitor']['effective_params']
    assert p['cmd_vel_in_topic']=='/limbo/nav2_preview/cmd_vel_smoothed'
    assert p['cmd_vel_out_topic']=='/limbo/nav2_preview/cmd_vel'
    assert not p['enable_stamped_cmd_vel']
    assert calls['lifecycle_manager_navigation']['parameters'][0]['node_names']==list(calls)[:-1]


def test_explicit_real_output_still_has_collision_monitor_last():
    calls=nodes('/cmd_vel')
    assert calls['collision_monitor']['effective_params']['cmd_vel_out_topic']=='/cmd_vel'
    assert dict(calls['controller_server']['remappings'])['cmd_vel']=='/cmd_vel_nav'
    assert dict(calls['velocity_smoother']['remappings'])['cmd_vel_smoothed']=='/cmd_vel_smoothed'


@pytest.mark.parametrize('name',['','relative','/','/cmd_vel_nav','/cmd_vel_smoothed',
                                      '/limbo/nav2_preview/cmd_vel_nav','/limbo/nav2_preview/cmd_vel_smoothed'])
def test_output_loop_or_ambiguous_name_rejected(name):
    with pytest.raises(ValueError):nodes(name)


def test_real_amcl_requires_explicit_initial_pose():
    p=ROOT/'limbo/src/limbo_navigation/config/amcl_real.yaml'
    cfg=yaml.safe_load(p.read_text())['amcl']['ros__parameters']
    assert cfg['set_initial_pose'] is False
    assert 'initial_pose' not in cfg
    assert 'yaml_filename' not in yaml.safe_load(p.read_text())['map_server']['ros__parameters']
