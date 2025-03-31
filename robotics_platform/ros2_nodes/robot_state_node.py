import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import time

class RobotStateNode(Node):
    def __init__(self):
        super().__init__('robot_state_node')
        
        # Create publishers for robot state
        self.emoji_publisher = self.create_publisher(
            String,
            'robot/emoji',
            10)
            
        self.log_publisher = self.create_publisher(
            String,
            'robot/logs',
            10)
            
        # Timer for periodic state updates
        self.timer = self.create_timer(1.0, self.timer_callback)
        
        self.get_logger().info('Robot State Node initialized')
        
    def timer_callback(self):
        # Publish robot state
        emoji_msg = String()
        emoji_msg.data = '🤖'
        self.emoji_publisher.publish(emoji_msg)
        
        log_msg = String()
        log_msg.data = f"Robot active - {time.strftime('%H:%M:%S')}"
        self.log_publisher.publish(log_msg)
        
        self.get_logger().info('Published robot state')

def main(args=None):
    rclpy.init(args=args)
    node = RobotStateNode()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
