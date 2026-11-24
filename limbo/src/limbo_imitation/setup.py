from glob import glob

from setuptools import find_packages, setup

package_name = 'limbo_imitation'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='david',
    maintainer_email='kimkihyun123455@gmail.com',
    description='조이스틱 주행 기록·모방 학습용 명령 중재·바퀴 단위 지표',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'drive_arbiter = limbo_imitation.drive_arbiter:main',
            'run_recorder = limbo_imitation.run_recorder:main',
            'collect_metrics = limbo_imitation.collect_metrics:main',
        ],
    },
)
