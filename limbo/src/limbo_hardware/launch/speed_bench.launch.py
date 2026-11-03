"""Explicit one-goal bench session; no Nav2, no automatic start command."""
import os
import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _nodes(context):
    get=lambda key:LaunchConfiguration(key).perform(context)
    with open(get('encoder_params_file'),encoding='utf-8') as f:
        enc=yaml.safe_load(f)['roboclaw_encoder']['ros__parameters']
    with open(get('odom_params_file'),encoding='utf-8') as f:
        odom=yaml.safe_load(f)['wheel_odometry']['ros__parameters']
    parameters={key:float(odom[key]) for key in ('left_wheel_radius','right_wheel_radius','wheel_separation')}
    parameters.update({key:float(enc[key]) for key in ('left_counts_per_revolution','right_counts_per_revolution')})
    parameters.update({key:float(get(key)) for key in ('left_target_rad_s','right_target_rad_s','duration_seconds','kp','ki','velocity_window_s','feedforward_gain','left_feedforward_gain','right_feedforward_gain')})
    parameters['max_duty_raw']=int(get('max_duty_raw'))
    for key in ('extended_observation','extended_distance_observation','record_voltage'):
        value=get(key).lower()
        if value not in ('true','false'):raise ValueError(key+' must be true or false')
        parameters[key]=value=='true' 
    parameters.update(use_sim_time=False,enable_output=get('enable_output').lower()=='true',record_dir=get('record_dir'))
    return [Node(package='limbo_hardware',executable='wheel_speed_bench',name='wheel_speed_bench',
                 output='screen',parameters=[parameters])]


def generate_launch_description():
    share=get_package_share_directory('limbo_hardware')
    defaults={'encoder_params_file':os.path.join(share,'config/encoders_readonly.yaml'),
              'odom_params_file':os.path.join(share,'config/wheel_odometry.yaml'),
              'left_target_rad_s':'0.0','right_target_rad_s':'0.0','duration_seconds':'5.0',
              'kp':'0.10','ki':'0.20','max_duty_raw':'3276','velocity_window_s':'0.20',
              'feedforward_gain':'0.0',
              'left_feedforward_gain':'-1.0','right_feedforward_gain':'-1.0',
              'enable_output':'false','extended_observation':'false',
              'extended_distance_observation':'false','record_voltage':'false','record_dir':''}
    return LaunchDescription([*[DeclareLaunchArgument(k,default_value=v) for k,v in defaults.items()],OpaqueFunction(function=_nodes)])
