"""human_layer로 보내는 PersonPredictionArray 메시지 변환."""

from geometry_msgs.msg import Point
from limbo_interfaces.msg import PersonPrediction, PersonPredictionArray


def prediction_array(predictions, frame_id, stamp):
    """예측 결과(PredictedPerson) 목록을 PersonPredictionArray로 바꾼다."""
    msg = PersonPredictionArray()
    msg.header.stamp = stamp
    msg.header.frame_id = frame_id

    for person in predictions:
        prediction = PersonPrediction()

        # Limbo Track Manager가 관리하는 안정적인 person ID
        prediction.person_id = int(person.track_id)

        prediction.current_position.x = float(person.current_x)
        prediction.current_position.y = float(person.current_y)
        prediction.current_position.z = 0.0

        prediction.velocity.x = float(person.vx)
        prediction.velocity.y = float(person.vy)
        prediction.velocity.z = 0.0

        for future_x, future_y, t in person.points:
            point = Point()
            point.x = float(future_x)
            point.y = float(future_y)
            point.z = 0.0
            prediction.predicted_positions.append(point)
            prediction.time_offsets.append(float(t))

        msg.predictions.append(prediction)

    return msg
