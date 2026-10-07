from setuptools import find_packages, setup

package_name = 'limbo_monitor'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', ['config/wheel_slip_monitor.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ktj',
    maintainer_email='troubadour900@gmail.com',
    description='주행 중 이상 상황(바퀴 헛돎 등)을 감시하는 노드',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'wheel_slip_monitor = limbo_monitor.wheel_slip_monitor:main',
        ],
    },
)
