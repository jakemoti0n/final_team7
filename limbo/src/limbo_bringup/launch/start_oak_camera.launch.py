"""OAK RGB-D만 Limbo 입력 토픽으로 발행한다. 실물 장착 TF는 별도로 설정한다."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import SetRemap


def generate_launch_description():
    bringup_dir = get_package_share_directory('limbo_bringup')
    driver_dir = get_package_share_directory('depthai_ros_driver_v3')

    # 영상 데이터, 단위, 촬영 시각, optical frame은 드라이버 값을 그대로 쓴다.
    # RGB와 깊이 CameraInfo는 서로 다른 촬영 시각을 가지므로 한 토픽으로 합치지 않는다.
    remappings = [
        ('/oak/rgb/image_raw', '/rgbd_camera/image'),
        ('/oak/stereo/image_raw', '/rgbd_camera/depth_image'),
        ('/oak/rgb/camera_info', '/rgbd_camera/camera_info'),
        ('/oak/stereo/camera_info', '/rgbd_camera/depth_camera_info'),
    ]

    camera = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(driver_dir, 'launch', 'driver.launch.py')),
        launch_arguments={
            'params_file': LaunchConfiguration('params_file'),
            'name': 'oak',
            'namespace': '',
            'camera_model': 'OAK-D-LITE',
            'use_rviz': 'false',
            'rs_compat': 'false',
            'pointcloud.enable': 'false',
            # 카메라 자체 TF 트리만 발행한다. 로봇 base_link와 연결한 값이 아니다.
            # oak_rgb_camera_optical_frame 이름을 임의로 로봇 frame으로 바꾸지 않는다.
            'parent_frame': 'oak_device_frame',
            'cam_pos_x': '0.0',
            'cam_pos_y': '0.0',
            'cam_pos_z': '0.0',
            'cam_roll': '0.0',
            'cam_pitch': '0.0',
            'cam_yaw': '0.0',
            'publish_tf_from_calibration': 'true',
            'imu_from_descr': 'false',
        }.items(),
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=os.path.join(bringup_dir, 'config', 'oak_usb2_rgbd.yaml'),
            description='OAK RGB-D 설정 파일. 기본: USB 2, 640x400, 10 Hz, NN 비활성.',
        ),
        # Include 내부의 composable driver에도 remap을 전달하고 이 그룹에만 한정한다.
        GroupAction(
            scoped=True,
            actions=[SetRemap(src=source, dst=target) for source, target in remappings] + [camera],
        ),
    ])
