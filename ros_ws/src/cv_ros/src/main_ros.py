# !/usr/bin/env python

import __init__
from cv_lib.src.object_detection import ObjectDetector
from cv_lib.src.camera_listener import CameraListener
from cv_lib.src.object_prediction import ObjectPredictor
from cv_lib.src.myUtils import draw_bboxes
from cv_ros.msg import ObjectPose
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String
import tf2_ros, rospy, torch, cv2

# topics list
topic_rs_status = '/RS_status'
topic_cv_status = '/CV_status'
topic_cv_data = '/CV_data'

class PosePublisher():

    def __init__(self):
        rospy.init_node("Vision")
        self.pub = rospy.Publisher(topic_cv_data, ObjectPose, queue_size=10)
        self.pub_state = rospy.Publisher(topic_cv_status, String, queue_size=10)
        self.msg = ObjectPose()
        self.cv_status = String()
        self.buffer = tf2_ros.Buffer()
        self.rate = rospy.Rate(10)

    def publish_pose(self, centroid_coo, plane_vector_coo, seq_id, object_type):
        self.msg.header.frame_id, self.msg.header.stamp, self.msg.header.seq, self.msg.object_type = "camera", rospy.Time.now(), seq_id, String(object_type)

        for centroid, plane, i in zip(centroid_coo, plane_vector_coo, range(len(centroid_coo))):
            p = PoseStamped()
            p.header.frame_id, p.header.seq = 'camera', i
            p.pose.position.x = centroid[0]
            p.pose.position.y = centroid[1]
            p.pose.position.z = centroid[2]
            print("coordinates : {}".format(centroid))

            [p.pose.orientation.x, p.pose.orientation.y, p.pose.orientation.z] = plane
            #p = self.transform_cam_to_world_coo_cb(self, p)
            self.msg.poses.append(p)

        self.pub.publish(self.msg)
        seq_id += 1
        self.msg.poses.clear()

    def publish_status(self):
        self.pub_state.publish(self.cv_status)

    def set_status(self, str='IDLE'):
        self.cv_status.data = str

    """def transform_cam_to_world_coo_cb(self, data):
        trans = self.buffer.lookup_transform("world", "camera", rospy.Time(0))  # data.header.stamp)
        data.header.frame_id = "world"
        rot = quaternion.quaternion()
        rot.x = trans.transform.rotation.x
        rot.y = trans.transform.rotation.y
        rot.z = trans.transform.rotation.z
        rot.w = trans.transform.rotation.w

        pos = quaternion.from_float_array([0, data.pose.position.x, data.pose.position.y, data.pose.position.z])
        pos = rot * pos * rot.inverse()
        [data.pose.position.x, data.pose.position.y, data.pose.position.z] = quaternion.as_vector_part(pos)

        normal_vec = quaternion.from_float_array(
            [0, data.pose.orientation.x, data.pose.orientation.y, data.pose.orientation.z])
        normal_vec = rot * normal_vec * rot.inverse()
        [data.pose.orientation.x, data.pose.orientation.y, data.pose.orientation.z] = quaternion.as_vector_part(
            normal_vec)

        data.pose.position.x += trans.transform.translation.x
        data.pose.position.y += trans.transform.translation.y
        data.pose.position.z += trans.transform.translation.z

        return data"""


def run():
    publisher = PosePublisher()

    # device
    cuda_available = torch.cuda.is_available()
    device = torch.device("cuda:0" if cuda_available else "cpu")

    # start camera listener and detector
    camera = CameraListener()
    detector = ObjectDetector()
    predictor = ObjectPredictor(device, model_name='Resnet50_FPN')
    publisher.set_status()

    # counter
    i = 0

    while not rospy.is_shutdown():

        # Wait for Robotic station status
        rs_status = rospy.wait_for_message(topic_rs_status, String)  # will be always active, otherwise code stops here
        if rs_status.data == 'STANDSTILL':

            # Take picture
            camera.get_frames()
            camera.get_info()

            # detect plant_holder
            detector.set_picture(camera.bgr_image)
            detector.get_mask(it=2)
            found_plantHolders = detector.find_centroids(threshold=1000, verbose=False)
            # Find positions and orientations
            detector.get_pos(camera, verbose=False)
            detector.get_plane_orientation(camera, plot=False)

            # detect flowers
            cv2.imshow("test", camera.bgr_image)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
            poses, found_flowers = predictor(camera.bgr_image, camera, conf = 0.8, verbose=True)

            if found_plantHolders:
                publisher.set_status('SUCCESS')
                publisher.publish_pose(detector.coo, detector.planes, i, 'plant_holders')
                detector.reset()
            if found_flowers:
                publisher.set_status('SUCCESS')
                publisher.publish_pose(poses['centroids_coo'][:,:3], poses['centroids_coo'][:,:3], i, 'flowers')

            else:
                publisher.set_status('RETRY')
        publisher.publish_status()
        publisher.rate.sleep()

if __name__ == '__main__':
    run()