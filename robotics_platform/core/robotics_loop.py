import time
import threading
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from robotics_platform.ui.pygame_ui import PygameUI
from robotics_platform.ros2_nodes.ui_interface_node import UIInterfaceNode

class RoboticsLoop:
    def __init__(self):
        self.ui = PygameUI()
        self.running = True
        
        # Create the ROS2 node for UI interface
        self.ui_node = UIInterfaceNode(self.ui)
        
        # Start ROS2 executor in separate thread
        self.executor = rclpy.executors.SingleThreadedExecutor()
        self.executor.add_node(self.ui_node)
        self.ros_thread = threading.Thread(target=self.run_ros_executor, daemon=True)

    def run_ros_executor(self):
        while self.running:
            self.executor.spin_once(timeout_sec=0.1)
            time.sleep(0.01)

    def run(self):
        self.ui.start()
        self.ros_thread.start()
        
        try:
            while self.running:
                # Main robotics loop, most control now happens in ROS2 nodes
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.running = False
        finally:
            self.ui.stop()
            self.ui_node.destroy_node()
