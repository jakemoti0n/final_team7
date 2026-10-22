from setuptools import find_packages, setup

package_name = 'limbo_follow'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', ['config/follow.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='david',
    maintainer_email='kimkihyun123455@gmail.com',
    description='등록한 운용자(직원)를 일정 거리 두고 따라가는 노드 (PROJECT.md 2-9)',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'follow_node = limbo_follow.follow_node:main',
        ],
    },
)
