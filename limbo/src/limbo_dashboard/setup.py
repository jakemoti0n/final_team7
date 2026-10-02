from glob import glob
import os

from setuptools import find_packages, setup


package_name = 'limbo_dashboard'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'web'), glob('web/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='david',
    maintainer_email='kimkihyun123455@gmail.com',
    description='Read-only ROS 2 monitoring dashboard for Limbo',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'dashboard = limbo_dashboard.server:main',
        ],
    },
)
