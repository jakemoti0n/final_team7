# Pinky generated Xacro

Target:
- ROS 2 Jazzy
- Gazebo Harmonic
- RViz 2
- Differential drive: 2 powered wheels
- Passive casters: front 1 + rear 1

## Coordinate convention

- X = forward
- Y = left
- Z = up

Nominal target envelope:
- 0.45 x 0.45 x 0.60 m

Drive wheel geometry:
- diameter: 0.100 m
- width: 0.030 m
- center separation: 0.300913 m

Wheel centers:
- left:  (0, +0.1504565, 0.050) m
- right: (0, -0.1504565, 0.050) m

Caster assembly centers:
- front: (+0.1058614, 0, 0.0448313) m
- rear:  (-0.1058614, 0, 0.0448313) m

## Temporary mass model

The real robot is expected to be 17-25 kg.
This first model uses 21.0 kg:

- body: 18.8 kg
- left wheel: 0.7 kg
- right wheel: 0.7 kg
- front caster: 0.4 kg
- rear caster: 0.4 kg

Replace these values after the real hardware mass is known.

## Caster model

The caster STL is used as the visual mesh.

For initial Gazebo physics, each caster uses:
- fixed joint
- low-friction spherical collision

This is a deliberate simplification for stable differential-drive testing.
If caster motion looks unrealistic later, split each caster into:
1. swivel bracket link,
2. caster wheel link,
3. swivel joint,
4. rolling joint.

## Copy into your existing pinky_description package

Generated folders:

- urdf/
- meshes/
- launch/
- params/

The Xacro mesh URI assumes the package name is exactly:

    pinky_description

Make sure CMakeLists.txt installs these directories.
See:

    CMakeLists_additions.txt

Then rebuild:

    cd ~/pinky
    colcon build --symlink-install
    source install/setup.bash

## RViz test

    ros2 launch pinky_description display_generated.launch.py

In RViz, set Fixed Frame to:

    base_link

or:

    base_footprint

## Gazebo Harmonic test

If needed:

    sudo apt install ros-jazzy-ros-gz

Run:

    ros2 launch pinky_description gazebo_generated.launch.py

Forward test:

    ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.2}, angular: {z: 0.0}}"

Rotation test:

    ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0}, angular: {z: 0.5}}"

Check:

    ros2 topic echo /odom --once
    ros2 topic echo /joint_states --once

## Values that should be tuned later

1. Actual total mass.
2. Actual center of mass.
3. Body collision geometry.
4. Wheel-floor friction.
5. Detailed caster physics.
6. LiDAR / camera links and Gazebo sensors.
7. Nav2 footprint.

For Nav2, start from the real 0.45 x 0.45 m outer envelope.
