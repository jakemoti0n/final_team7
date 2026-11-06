"""Near-depth cleanup for navigation, then XYZ projection and 5 cm voxels."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import IfElseSubstitution, LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    enabled = LaunchConfiguration('filter_near_depth')
    depth_input = IfElseSubstitution(enabled, if_value='/rgbd_camera/depth_for_points',
                                     else_value='/rgbd_camera/depth_image')
    return LaunchDescription([
        DeclareLaunchArgument('filter_near_depth', default_value='false', choices=['true', 'false']),
        Node(package='limbo_bringup', executable='near_depth_filter.py', name='real_near_depth_filter',
             condition=IfCondition(enabled),
             output='screen', parameters=[{'use_sim_time': False}],
             remappings=[('depth_in', '/rgbd_camera/depth_image'),
                         ('depth_out', '/rgbd_camera/depth_for_points')]),
        Node(package='depth_image_proc', executable='point_cloud_xyz_node', name='real_depth_points',
             output='screen', parameters=[{'use_sim_time': False, 'queue_size': 2}],
             remappings=[('image_rect', depth_input),
                         ('camera_info', '/rgbd_camera/depth_camera_info'),
                         # image_transport derives camera_info after resolving image_rect.
                         ('/rgbd_camera/camera_info', '/rgbd_camera/depth_camera_info'),
                         ('points', '/rgbd_camera/points_raw')]),
        Node(package='pcl_ros', executable='filter_voxel_grid_node', name='real_rgbd_voxel',
             output='screen', parameters=[{'use_sim_time': False, 'leaf_size': 0.05}],
             remappings=[('input', '/rgbd_camera/points_raw'), ('output', '/rgbd_camera/points')]),
    ])
