from setuptools import find_packages, setup

package_name = 'limbo_perception'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config',
            ['config/person_detector.yaml', 'config/person_detector_oak.yaml',
             'config/oak_camera.yaml', 'config/tof.yaml', 'config/person_wait.yaml']),
        # 팀원이 학습한 하반신 모델 (person_detector.yaml 기본 모델)과 그것을 OAK 카메라 안에서 돌리는 blob
        ('share/' + package_name + '/models',
            ['models/leg_512.pt', 'models/leg_640.pt', 'models/leg_640_352_3shave.blob']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='david',
    maintainer_email='kimkihyun123455@gmail.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'person_detector = limbo_perception.person_detector:main',
            'tof_node = limbo_perception.tof_node:main',
            'person_wait = limbo_perception.person_wait_node:main',
            'oak_camera = limbo_perception.oak_camera:main',
        ],
    },
)
