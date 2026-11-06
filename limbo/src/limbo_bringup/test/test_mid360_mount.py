"""Sensor-to-body geometry regression; imports launch only, opens no devices."""
import copy, importlib.util, json, math, sys
from pathlib import Path
import pytest
from unittest.mock import Mock,patch
from launch import LaunchContext

ROOT=Path(__file__).resolve().parents[1]/'launch'
spec=importlib.util.spec_from_file_location('mid360_rotation_test',ROOT/'start_mid360.launch.py')
launch=importlib.util.module_from_spec(spec);spec.loader.exec_module(launch)
BASE={'parent_frame':'base_footprint','sensor_frame':'mid360_link',
      'sensor_translation_m':[.1,-.05,.837], 'sensor_rpy_rad':[0.,0.,0.],
      'body_min_base_m':[-.2,-.3,0.], 'body_max_base_m':[.4,.3,.79],
      'body_padding_m':.01,'scan_min_height_sensor_m':-.15,'scan_max_height_sensor_m':.2}

@pytest.mark.parametrize('yaw,lo,hi',[
    (0,[-.31,-.26,-.847],[.31,.36,-.037]),
    (math.pi/2,[-.26,-.31,-.847],[.36,.31,-.037]),
    (-math.pi/2,[-.36,-.31,-.847],[.26,.31,-.037]),
    (math.pi,[-.31,-.36,-.847],[.31,.26,-.037]),
])
def test_inverse_rotated_offset_nonsquare_body(yaw,lo,hi):
    c=copy.deepcopy(BASE);c['sensor_rpy_rad'][2]=yaw
    result=launch.mounted_parameters(c)
    assert result['body_min']==pytest.approx(lo)
    assert result['body_max']==pytest.approx(hi)

@pytest.mark.parametrize('rpy',[[0,0,math.pi/4],[.01,0,0],[0,.01,0],[0,0,float('nan')]])
def test_reject_geometry_not_exactly_representable(rpy):
    c=copy.deepcopy(BASE);c['sensor_rpy_rad']=rpy
    with pytest.raises(ValueError):launch.mounted_parameters(c)

def test_yaw_is_published_once_without_rotating_raw_driver_points(tmp_path):
    c=copy.deepcopy(BASE);c['sensor_rpy_rad'][2]=math.pi/2
    f=tmp_path/'mount.json';f.write_text(json.dumps(c))
    context=LaunchContext();context.launch_configurations.update(profile='mounted',mount_config_path=str(f))
    with patch.object(launch,'Node',Mock()) as node:launch.launch_nodes(context)
    calls=[call.kwargs for call in node.call_args_list]
    tf=next(n for n in calls if n['name']=='limbo_mid360_mount_tf')['arguments']
    assert float(tf[tf.index('--yaw')+1])==math.pi/2
    assert tf[tf.index('--frame-id')+1]=='base_footprint'
    assert tf[tf.index('--child-frame-id')+1]=='mid360_link'
    assert len([n for n in calls if n['package']=='tf2_ros'])==1
    scan=next(n for n in calls if n['package']=='pointcloud_to_laserscan')
    assert scan['parameters'][0]['target_frame']=='mid360_link'
    assert next(n for n in calls if n['name']=='lidar_cloud_guard')['parameters'][0]['body_min']==pytest.approx([-.26,-.31,-.847])
