from setuptools import setup

setup(
    name='limbo_telemetry_bridge', version='1.0.0',
    packages=['limbo_telemetry_bridge'],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/limbo_telemetry_bridge']),
        ('share/limbo_telemetry_bridge', ['package.xml']),
        ('share/limbo_telemetry_bridge/config', ['config/bridge.yaml']),
    ],
    install_requires=['setuptools', 'aiohttp>=3.9,<4', 'PyYAML>=6,<7'],
    entry_points={'console_scripts': [
        'bridge = limbo_telemetry_bridge.node:main',
    ]},
)
