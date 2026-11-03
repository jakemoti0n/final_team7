# One CRC-verified combined RoboClaw read. Header is host ROS receive time;
# RoboClaw supplies no hardware acquisition timestamp for this command.
std_msgs/Header header
# New UUID on every successful connection. Never integrate across session IDs.
string session_id
uint64 sequence
# First sample after connection: relative totals/deltas are zero, velocity unknown.
bool baseline
# Unsigned wrapping hardware counters, untouched by this node.
uint32 m1_raw
uint32 m2_raw
# Forward-positive counts, relative to this connection's first reading.
# Physical mapping: right=M1 (+), left=M2 (-).
int64 right_delta
int64 left_delta
int64 right_total
int64 left_total
