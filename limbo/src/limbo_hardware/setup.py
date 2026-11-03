from glob import glob
from setuptools import find_packages, setup

setup(
    name='limbo_hardware', version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/limbo_hardware']),
        ('share/limbo_hardware', ['package.xml']),
        ('share/limbo_hardware/launch', glob('launch/*.launch.py')),
        ('share/limbo_hardware/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='david', maintainer_email='kimkihyun123455@gmail.com',
    description='Read-only physical encoder input for Limbo.', license='Apache-2.0',
    entry_points={'console_scripts': [
        'roboclaw_encoder = limbo_hardware.encoder_node:main',
        'wheel_odometry = limbo_hardware.odometry_node:main',
        'drive_preview = limbo_hardware.drive_preview_node:main',
        'wheel_speed_bench = limbo_hardware.speed_bench_node:main',
        'roboclaw_drive = limbo_hardware.drive_node:main',
    ]},
)
