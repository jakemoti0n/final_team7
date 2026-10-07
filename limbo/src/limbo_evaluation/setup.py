from setuptools import find_packages, setup

package_name = 'limbo_evaluation'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', ['config/nav_recorder.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ktj',
    maintainer_email='troubadour900@gmail.com',
    description='시뮬레이션 주행을 정답 위치 기준으로 평가해 CSV로 남기는 노드',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'nav_recorder = limbo_evaluation.nav_recorder:main',
        ],
    },
)
