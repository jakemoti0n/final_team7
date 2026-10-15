from setuptools import find_packages, setup

package_name = 'limbo_drive'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ktj',
    maintainer_email='troubadour900@gmail.com',
    description='사람이 로봇을 모는 조종 관문(데드맨·속도 상한)과 지도 작성 상태 표시',
    license='TODO: License declaration',
    extras_require={'test': ['pytest']},
    entry_points={
        'console_scripts': [
            'drive_gate = limbo_drive.drive_gate:main',
            'map_status = limbo_drive.map_status:main',
        ],
    },
)
